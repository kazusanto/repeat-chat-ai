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

_debug_ = True

LEARNER_LANGUAGE = "English"
FEEDBACK_LANGUAGE = "Japanese"

OPENAI_MODEL = "gpt-4.1-mini"

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

def build_turn_commands(idx, role, text, translation=""):
    commands = [{"type": "show_message", "role": role, "text": text, "translation": translation}]
    sentences = split_sentences(text)
    for i, sentence in enumerate(sentences):
        filename = f"tmp_{idx}_{i}.mp3"
        write_tts_file(sentence, filename)
        commands.append({"type": "show_sentence", "role": role, "text": sentence})
        commands.append({"type": "speak", "file": filename})
        commands.append({"type": "pause", "repeat": {"type": "speak", "file": filename}})
        commands.append({"type": "cleanup", "file": filename})
    return commands

def write_tts_file(text, filename):
    try:
        debug(f'write_tts_file("{text}", {filename})')
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
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
        # still attempt immediate cleanup if possible
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
    debug(script)

    try:
        while True:
            if not prefetching and len(output_queue) < 4:
                prefetching = True

                def do_prefetch(captured_idx):
                    nonlocal prefetching
                    if captured_idx < len(script):
                        turn = script[captured_idx]
                        commands = build_turn_commands(captured_idx, turn["role"], turn["content"], turn.get("translation", ""))
                        output_queue.extend(commands)
                    prefetching = False

                threading.Thread(target=do_prefetch, args=(next_idx,)).start()
                next_idx += 1

            if not output_queue and next_idx >= len(script) and not prefetching:
                print("\nEnd of conversation")
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
    system_prompt = (
        f"You are creating a conversation script for language learning.\n\n"
        f"Scene topic: \"{scene}\"\n\n"
        f"Language rules:\n"
        f"- Use {LEARNER_LANGUAGE} for the characters' dialogue (first line of each turn).\n"
        f"- Use {FEEDBACK_LANGUAGE} for the translation (second line of each turn).\n"
        f"- Use {LEARNER_LANGUAGE} for the scene and role descriptions.\n\n"
        f"Formatting rules:\n"
        f"1. Output the scene description:\n"
        f"   Scene: <one-line scene description in {LEARNER_LANGUAGE}>\n"
        f"2. Output the two roles:\n"
        f"   Role A: <A's character description in {LEARNER_LANGUAGE}>\n"
        f"   Role B: <B's character description in {LEARNER_LANGUAGE}>\n"
        f"3. Then write 6-10 turns of conversation, alternating A and B.\n"
        f"4. Each turn must follow this two-line format exactly:\n"
        f"   A: <sentence in {LEARNER_LANGUAGE}>\n"
        f"   → <translation in {FEEDBACK_LANGUAGE}>\n"
        f"5. Start with A. Do not include explanations, commentary, or blank lines.\n\n"
        f"Example (when {LEARNER_LANGUAGE} = English and {FEEDBACK_LANGUAGE} = Japanese):\n\n"
        f"Scene: At a café\n"
        f"Role A: A university student studying for exams.\n"
        f"Role B: A barista who loves to chat with customers.\n\n"
        f"A: Do you have any new seasonal drinks today?\n"
        f"→ 今日のおすすめの季節限定ドリンクはありますか？\n\n"
        f"B: Yes! We have a maple cinnamon latte.\n"
        f"→ はい、メープルシナモンラテがありますよ。\n\n"
        f"...\n\n"
        f"Make sure the format and language rules are followed strictly."
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=1200,
        temperature=0.8,
    )
    text = response.choices[0].message.content.strip()
    lines = text.splitlines()
    scene_title = ""
    roles = {}
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
        elif line.startswith("A:") or line.startswith("B:"):
            role = line[0]
            text = clean_text(line[2:].strip())
            translation = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("→"):
                translation = clean_text(lines[i + 1][1:].strip())
                i += 1
            script.append({"role": role, "content": text, "translation": translation})
        i += 1

    return {
        "scene": scene_title,
        "roles": roles,
        "script": script,
    }

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
