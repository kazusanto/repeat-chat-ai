#!/usr/bin/env python3
import openai
import os
import sys
import termios
import tty
import re
from collections import deque
import threading
import time
import atexit
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

DEBUG = False

LEARNER_LANGUAGE = "English"
FEEDBACK_LANGUAGE = "Japanese"

OPENAI_MODEL = "gpt-4.1-mini"

MALE_VOICES = ["alloy", "fable"]
FEMALE_VOICES = ["nova", "shimmer"]

try:
    client = openai.OpenAI(timeout=10)  # Attempt to use OPENAI_API_KEY from env
except openai.OpenAIError:
    api_key = input("Enter your OpenAI API key: ")
    client = openai.OpenAI(api_key=api_key, timeout=10)

cleanup_files = []
queue_lock = threading.Lock()
is_first_prompt = True

def debug_out(str):
    if DEBUG:
        print(f'[debug] {str}', file=sys.stderr)

def mark_for_cleanup(file):
    cleanup_files.append(file)

def final_cleanup():
    for file in cleanup_files:
        try:
            os.remove(file)
            debug_out(f"Final cleanup: {file} deleted")
        except FileNotFoundError:
            pass

atexit.register(final_cleanup)

def build_turn_commands(idx, role, text, translation="", voice="alloy"):
    commands = [{"type": "show_message", "role": role, "text": text, "translation": translation}]
    sentences = split_sentences(text)
    translations = split_sentences(translation)
    for i, sentence in enumerate(sentences):
        translated = translations[i] if i < len(translations) else ""
        filename = f"tmp_{idx}_{i}.mp3"
        fetch_text_to_speech(sentence, filename, voice)
        commands.append({"type": "show_sentence", "role": role, "text": sentence, "translation": translated})
        commands.append({"type": "speak", "file": filename})
        commands.append({"type": "pause", "repeat": {"type": "speak", "file": filename}})
        commands.append({"type": "cleanup", "file": filename})
    return commands

def fetch_text_to_speech(text, filename, voice):
    try:
        debug_out(f'fetch_text_to_speech("{text}", {filename}, {voice})')
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        mark_for_cleanup(filename)
        with open(filename, "wb") as f:
            f.write(speech_response.content)
        debug_out(f'{filename} has created.')
    except Exception as e:
        print(str(e))

def play_audio(filename):
    debug_out(f'play_audio({filename})')
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
    except Exception as e:
        print(f"Audio playback failed: {e}")

def clean_text(text):
    return text.strip().strip('"“”')

def split_sentences(text):
    return [s.strip() for s in text.split("|")]

def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = sys.stdin.read(1)
            if key in (" ", "\n"):
                return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def do_command(command, output_queue):
    if command["type"] == "show_message":
        debug_out("--------")
        debug_out(f'{command["role"]}: {command["text"]}')
        debug_out(f'→ {command["translation"]}')
        debug_out("--------")
    elif command["type"] == "show_sentence":
        print(f'{command["role"]}: {command["text"]}')
        if "translation" in command and command["translation"]:
            print(f'→ {command["translation"]}')
    elif command["type"] == "speak":
        play_audio(command["file"])
    elif command["type"] == "pause":
        global is_first_prompt
        prompt = "[press space to repeat, enter for next]> " if is_first_prompt else "> "
        is_first_prompt = False
        print(prompt, end="", flush=True)
        key = get_key()
        print()
        if key == " ":
            output_queue.appendleft(command)  # pause again
            output_queue.appendleft(command["repeat"])  # repeat the associated action
    elif command["type"] == "cleanup":
        try:
            os.remove(command["file"])
            debug_out(f'{command["file"]} has been removed')
        except FileNotFoundError:
            pass

def repl(scenario):
    script = scenario.get("script", [])
    output_queue = deque()
    next_idx = 0
    prefetching = False

    try:
        while True:
            if not prefetching and len(output_queue) < 4:
                prefetching = True

                def do_prefetch(captured_idx):
                    nonlocal prefetching
                    if captured_idx < len(script):
                        turn = script[captured_idx]
                        role = turn['role']
                        voice = scenario["voices"].get(role, MALE_VOICES[0])
                        commands = build_turn_commands(captured_idx, turn["role"], turn["content"], turn.get("translation", ""), voice)
                        output_queue.extend(commands)
                    prefetching = False

                threading.Thread(target=do_prefetch, args=(next_idx,)).start()
                next_idx += 1

            if not output_queue and next_idx >= len(script) and not prefetching:
                print("Finished.")
                break

            if output_queue:
                command = output_queue.popleft()
                do_command(command, output_queue)
            else:
                time.sleep(0.05)

    except KeyboardInterrupt:
        for command in list(output_queue):
            if command["type"] == "cleanup":
                do_command(command, output_queue)
        print("\nExiting repeat-chat-ai")

def generate_scenario(scene):
    system_prompt = (f"""
You are creating a conversation script for language learning.

Scene topic: \"{scene}\"

Language rules:
- Use {LEARNER_LANGUAGE} for the characters' dialogue (first line of each turn).
- Use {FEEDBACK_LANGUAGE} for the translation (second line of each turn).
- Use {LEARNER_LANGUAGE} for the scene and role descriptions.
- Provide translations for the scene description and each role description, immediately following them.

Formatting rules:

1. Output the scene description:
   Scene: <one-line scene description in {LEARNER_LANGUAGE}>
   → <translation of scene description in {FEEDBACK_LANGUAGE}>
2. Output the two roles:
   Role A: <A's character description in {LEARNER_LANGUAGE}>
   → <translation of A's role description in {FEEDBACK_LANGUAGE}>
   Role B: <B's character description in {LEARNER_LANGUAGE}>
   → <translation of B's role description in {FEEDBACK_LANGUAGE}>
3. Output the two voice types:
   Voice A: <A's voice type as male or female>
   Voice B: <B's voice type as male or female>
4. Then write 10-20 turns of conversation, alternating A and B.
   Make sure the dialogue flows naturally and ends with a reasonable conclusion, as it would in a real-life interaction.
   Keep the dialogue realistic and context-appropriate. Avoid overly enthusiastic or exaggerated expressions (e.g., "Great!", "Awesome!") unless the character's personality justifies it.
5. Each turn must follow this two-line format exactly:
   A: <sentence in {LEARNER_LANGUAGE} | ... >
   → <translation in {FEEDBACK_LANGUAGE} | ... >
   Use "|" to split each natural sentence segment. Ensure each natural {LEARNER_LANGUAGE} segment strictly matches the corresponding translated segment in order.
6. Start with A. Do not include explanations, commentary, or blank lines.

Make sure the format and language rules are followed strictly.
Example (when {LEARNER_LANGUAGE} = English and {FEEDBACK_LANGUAGE} = Japanese):

Scene: At a café
→ カフェで
Role A: A barista who loves to chat with customers
→ お客さんと話すのが好きなバリスタ
Role B: A university student studying for exams
→ 試験勉強をしている大学生
Voice A: male
Voice B: female

A: Hi there! | Studying hard today?
→ こんにちは！ | 今日も一生懸命勉強ですね？
B: Yeah, exams are coming up. | I needed a quiet spot and some caffeine.
→ はい、試験が近いんです。 | 静かな場所とカフェインが必要で。
A: You've come to the right place. | Want your usual latte?
→ それならここがぴったりですね。 | いつものラテにしますか？
B: Yes, please. | And maybe a muffin too.
→ はい、お願いします。 | それとマフィンもください。
...
""")

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=1200,
        temperature=0.8,
    )
    text = response.choices[0].message.content.strip()
    debug_out(text)
    lines = text.splitlines()
    scene_title = ""
    scene_translation = ""
    roles = {}
    roles_translation = {}
    gender = {}
    voices = {}
    script = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Scene:"):
            scene_title = clean_text(line[len("Scene:"):].strip())
            if i + 1 < len(lines) and lines[i + 1].startswith("→"):
                scene_translation = clean_text(lines[i + 1][1:].strip())
                i += 1
        elif line.startswith("Role A:"):
            roles["A"] = clean_text(line[len("Role A:"):].strip())
            if i + 1 < len(lines) and lines[i + 1].startswith("→"):
                roles_translation["A"] = clean_text(lines[i + 1][1:].strip())
                i += 1
        elif line.startswith("Role B:"):
            roles["B"] = clean_text(line[len("Role B:"):].strip())
            if i + 1 < len(lines) and lines[i + 1].startswith("→"):
                roles_translation["B"] = clean_text(lines[i + 1][1:].strip())
                i += 1
        elif line.startswith("Voice A:"):
            gender["A"] = line[len("Voice A:"):].strip()
        elif line.startswith("Voice B:"):
            gender["B"] = line[len("Voice B:"):].strip()
        elif line.startswith("A:") or line.startswith("B:"):
            role = line[0]
            text = clean_text(line[2:].strip())
            translation = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("→"):
                translation = clean_text(lines[i + 1][1:].strip())
                i += 1
            script.append({"role": role, "content": text, "translation": translation})
        i += 1

    voices["A"] = FEMALE_VOICES[0] if gender["A"].lower() == "female" else MALE_VOICES[0]
    voices["B"] = FEMALE_VOICES[1] if gender["B"].lower() == "female" else MALE_VOICES[1]

    scenario = {
        "scene": scene_title,
        "scene_translation": scene_translation,
        "roles": roles,
        "roles_translation": roles_translation,
        "voices": voices,
        "script": script,
    }
    debug_out(scenario)
    return scenario

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("Usage: repeat-chat-ai [scene]")
        print("If no scene is provided, defaults to 'at a café'.")
        sys.exit(0)
    try:
        pygame.mixer.init()
        scene = sys.argv[1] if len(sys.argv) > 1 else "at a café"
        scenario = generate_scenario(scene)
        print(f'scene: {scenario["scene"]} → {scenario["scene_translation"]}')
        print(f'role A: {scenario["roles"]["A"]} → {scenario["roles_translation"]["A"]}')
        print(f'role B: {scenario["roles"]["B"]} → {scenario["roles_translation"]["B"]}')
        repl(scenario)
    except KeyboardInterrupt:
        print("\nExiting repeat-chat-ai")
    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    main()
