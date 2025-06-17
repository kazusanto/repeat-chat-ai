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

_debug_ = False

LEARNER_LANGUAGE = "English"
FEEDBACK_LANGUAGE = "Japanese"

def debug(str):
    if _debug_:
        print(f'**** {str}')

def clean_text(text):
    return text.strip().strip('"“”')

def build_turn_commands(role, text, idx, translation=""):
    commands = [{"type": "show_message", "role": role, "text": text, "translation": translation}]
    sentences = split_sentences(text)
    for i, sentence in enumerate(sentences):
        filename = f"tmp_{idx}_{i}.mp3"
        text_to_speech(sentence, filename)
        commands.append({"type": "show_sentence", "role": role, "text": sentence})
        commands.append({"type": "speak", "file": filename})
        commands.append({"type": "pause", "repeat": {"type": "speak", "file": filename}})
        commands.append({"type": "cleanup", "file": filename})
    return commands

try:
    client = openai.OpenAI()  # Attempt to use OPENAI_API_KEY from env
except openai.OpenAIError:
    api_key = input("Enter your OpenAI API key: ")
    client = openai.OpenAI(api_key=api_key, timeout=10)

queue_lock = threading.Lock()

def build_history_for(role, history):
    """
    Convert role-based history (with roles A/B) into OpenAI API message format
    using 'user' and 'assistant' based on the target speaker.
    """
    result = []
    for msg in history:
        mapped_role = "assistant" if msg["role"] == role else "user"
        result.append({
            "role": mapped_role,
            "content": msg["content"]
        })
    return result

def generate_chat_message(role, history, scenario):
    debug(f'generate_chat_message({role}, history, scenario)')
    other_role = "B" if role == "A" else "A"
    system_prompt = (
        f"You are Role {role}: {scenario['roles'][role]}.\n"
        f"You are speaking to Role {other_role}: {scenario['roles'][other_role]}.\n"
        f"The scene is: {scenario['scene']}.\n"
        "Only reply with your line. Do not include names or role descriptions.\n"
        f"All your responses must be in {LEARNER_LANGUAGE}.\n"
        f"Your response must be two lines. First line: natural sentence in {LEARNER_LANGUAGE}. Second line: {FEEDBACK_LANGUAGE} translation.\n"
    )
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ] + build_history_for(role, history)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        max_tokens=60,
        temperature=0.9,
    )
    debug(f'message has generated')
    lines = response.choices[0].message.content.strip().split("\n", 1)
    text = clean_text(lines[0])
    translation = clean_text(lines[1]) if len(lines) > 1 else ""
    if not translation:
        print("Warning: No translation found in response")
    return text, translation

def text_to_speech(text, filename):
    try:
        debug(f'text_to_speech("{text}", {filename})')
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text,
            timeout=10
        )
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

def split_sentences(text):
    # Simple sentence splitter
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

first_prompt = True

def do_command(command, output_queue):
    if command["type"] == "print":
        print("--------")
        print(command["content"])
    elif command["type"] == "speak":
        play_audio(command["file"])
    elif command["type"] == "pause":
        global first_prompt
        prompt = "[press space to repeat, enter for next]> " if first_prompt else "> "
        first_prompt = False
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

def repl(scenario, first_message):
    history = []
    output_queue = deque()
    role = "A"
    lines = first_message.strip().split("\n", 1)
    text = clean_text(lines[0])
    translation = clean_text(lines[1]) if len(lines) > 1 else ""
    if not translation:
        print("Warning: No translation found in first message")
    history.append({"role": role, "content": text, "translation": translation})
    output_queue.extend(build_turn_commands(role, text, 0, translation))

    prefetching = False
    next_turn_data = None

    try:
        while True:
            if not prefetching and next_turn_data is None and len(output_queue) < 4:
                prefetching = True
                next_role = "B" if role == "A" else "A"
                next_idx = len(history)

                def do_prefetch(captured_idx):
                    nonlocal next_turn_data, prefetching
                    next_text, next_translation = generate_chat_message(next_role, history, scenario)
                    history.append({"role": next_role, "content": next_text, "translation": next_translation})
                    commands = build_turn_commands(next_role, next_text, captured_idx, next_translation)
                    with queue_lock:
                        next_turn_data = {"role": next_role, "idx": captured_idx, "commands": commands}
                        prefetching = False

                threading.Thread(target=do_prefetch, args=(next_idx,)).start()

            if not output_queue and next_turn_data:
                role = next_turn_data["role"]
                with queue_lock:
                    output_queue.extend(next_turn_data["commands"])
                    next_turn_data = None
                continue

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
        f"Given the scene '{scene}', create a natural conversation setup with two roles.\n"
        f"The output must be entirely in {LEARNER_LANGUAGE}, including role descriptions and the sample line.\n"
        f"Your sample line must be two lines: first in {LEARNER_LANGUAGE}, second is a {FEEDBACK_LANGUAGE} translation.\n"
        f"Output format:\n"
        f"Scene: <scene>\n"
        f"Role A: <description>\n"
        f"Role B: <description>\n"
        f"A: <first line>\n"
    )
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=150,
        temperature=0.8,
    )
    text = response.choices[0].message.content.strip()
    match = re.search(
        r"Scene:\s*(.+?)\nRole A:\s*(.+?)\nRole B:\s*(.+?)\nA:\s*(.+)",
        text,
        re.DOTALL
    )
    if match:
        return {
            "scene": match.group(1).strip(),
            "roles": {
                "A": match.group(2).strip(),
                "B": match.group(3).strip(),
            }
        }, clean_text(match.group(4))
    else:
        raise ValueError("Failed to parse scenario from response.")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("Usage: repeat-chat-ai [scene]")
        print("If no scene is provided, defaults to 'at a café'.")
        sys.exit(0)
    try:
        scene = sys.argv[1] if len(sys.argv) > 1 else "at a café"
        scenario, first_text = generate_scenario(scene)
        print(f'scene: {scenario["scene"]}')
        print(f'role A: {scenario["roles"]["A"]}')
        print(f'role B: {scenario["roles"]["B"]}')
        lines = first_text.strip().split("\n", 1)
        text = clean_text(lines[0])
        translation = clean_text(lines[1]) if len(lines) > 1 else ""
        if not translation:
            print("Warning: No translation found in first message")
        history = []
        output_queue = deque()
        role = "A"
        history.append({"role": role, "content": text, "translation": translation})
        output_queue.extend(build_turn_commands(role, text, 0, translation))
        repl(scenario, first_text)
    except KeyboardInterrupt:
        print("\nExiting repeat-chat-ai")

if __name__ == "__main__":
    main()
