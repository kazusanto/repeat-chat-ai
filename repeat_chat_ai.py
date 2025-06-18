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
import random

_debug_ = False

LEARNER_LANGUAGE = "English"
FEEDBACK_LANGUAGE = "Japanese"

OPENAI_MODEL = "gpt-4.1-mini"

MALE_VOICES = ["alloy", "fable"]
FEMALE_VOICES = ["nova", "shimmer"]

try:
    client = openai.OpenAI()  # Attempt to use OPENAI_API_KEY from env
except openai.OpenAIError:
    api_key = input("Enter your OpenAI API key: ")
    client = openai.OpenAI(api_key=api_key, timeout=10)

cleanup_files = []
queue_lock = threading.Lock()
is_first_prompt = True

def debug(str):
    if _debug_:
        print(f'**** {str}')

def mark_for_cleanup(file):
    cleanup_files.append(file)

def final_cleanup():
    for file in cleanup_files:
        try:
            os.remove(file)
            debug(f"Final cleanup: {file} deleted")
        except FileNotFoundError:
            pass

atexit.register(final_cleanup)

def build_turn_commands(idx, role, text, translation="", voice="alloy"):
    commands = [{"type": "show_message", "role": role, "text": text, "translation": translation}]
    sentences = split_sentences(text)
    for i, sentence in enumerate(sentences):
        filename = f"tmp_{idx}_{i}.mp3"
        fetch_text_to_speech(sentence, filename, voice)
        commands.append({"type": "show_sentence", "role": role, "text": sentence})
        commands.append({"type": "speak", "file": filename})
        commands.append({"type": "pause", "repeat": {"type": "speak", "file": filename}})
        commands.append({"type": "cleanup", "file": filename})
    return commands

def fetch_text_to_speech(text, filename, voice):
    try:
        debug(f'fetch_text_to_speech("{text}", {filename}, {voice})')
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            timeout=10
        )
        mark_for_cleanup(filename)
        with open(filename, "wb") as f:
            f.write(speech_response.content)
        debug(f'{filename} has created.')
    except Exception as e:
        print(str(e))

def play_audio(filename):
    debug(f'play_audio({filename})')
    if not os.path.exists(filename) or os.path.getsize(filename) < 100:
        print(f"Warning: Skipping playback of invalid or empty file: {filename}")
        return
    os.system(f'afplay "{filename}"')
    debug(f'{filename} has played')

def clean_text(text):
    return text.strip().strip('"“”')

def split_sentences(text):
    return [s.strip() for s in re.findall(r'[^.!?]+[.!?]', text)]

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
    if command["type"] == "print":
        print("--------")
        print(command["content"])
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
            debug(f'{command["file"]} has been removed')
        except FileNotFoundError:
            pass
    elif command["type"] == "show_message":
        print("--------")
        print(f'{command["role"]}: {command["text"]}')
        print(f'→ {command["translation"]}')
    elif command["type"] == "show_sentence":
        print("--------")
        print(f'{command["role"]}: {command["text"]}')

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

Formatting rules:

1. Output the scene description:
   Scene: <one-line scene description in {LEARNER_LANGUAGE}>
2. Output the two roles:
   Role A: <A's character description in {LEARNER_LANGUAGE}>
   Role B: <B's character description in {LEARNER_LANGUAGE}>
3. Output the two voice types:
   Voice A: <A's voice type as male or female>
   Voice B: <B's voice type as male or female>
4. Then write 6-12 turns of conversation, alternating A and B.
   Make sure the dialogue flows naturally and ends with a reasonable conclusion, as it would in a real-life interaction.
5. Each turn must follow this two-line format exactly:
   A: <sentence in {LEARNER_LANGUAGE}>
   → <translation in {FEEDBACK_LANGUAGE}>
6. Start with A. Do not include explanations, commentary, or blank lines.

Example (when {LEARNER_LANGUAGE} = English and {FEEDBACK_LANGUAGE} = Japanese):

Scene: At a café
Role A: A university student studying for exams.
Role B: A barista who loves to chat with customers.
Voice A: female
Voice B: male

A: Do you have any new seasonal drinks today?
→ 今日のおすすめの季節限定ドリンクはありますか？

B: Yes! We have a maple cinnamon latte.
→ はい、メープルシナモンラテがありますよ。
...
Make sure the format and language rules are followed strictly.
""")

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=1200,
        temperature=0.8,
    )
    text = response.choices[0].message.content.strip()
    debug(text)
    lines = text.splitlines()
    scene_title = ""
    roles = {}
    gender = {}
    voices = {}
    script = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Scene:"):
            scene_title = line[len("Scene:"):].strip()
        elif line.startswith("Role A:"):
            roles["A"] = line[len("Role A:"):].strip()
        elif line.startswith("Role B:"):
            roles["B"] = line[len("Role B:"):].strip()
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
        "roles": roles,
        "voices": voices,
        "script": script,
    }
    debug(scenario)
    return scenario

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("Usage: repeat-chat-ai [scene]")
        print("If no scene is provided, defaults to 'at a café'.")
        sys.exit(0)
    try:
        scene = sys.argv[1] if len(sys.argv) > 1 else "at a café"
        scenario = generate_scenario(scene)
        print(f'scene: {scenario["scene"]}')
        print(f'role A: {scenario["roles"]["A"]}')
        print(f'role B: {scenario["roles"]["B"]}')
        repl(scenario)
    except KeyboardInterrupt:
        print("\nExiting repeat-chat-ai")

if __name__ == "__main__":
    main()
