# repeat-chat-ai

## Summary

A CLI tool for language learning with repeatable, AI-generated conversations.

This tool simulates a chat environment where users can practice speaking in a foreign language by repeating AI-generated dialogues. It is designed to help learners improve their speaking skills through repetition and role-based interactions.

Default settings support Japanese speakers learning English, but other language pairs are configurable.

## Features

- Non-interactive chat simulation
- TTS (Text-to-Speech) support for both roles
- Lines can be read aloud, listened to, and repeated for practice
- Repeats each line for practice
- Role-based conversations with customizable scenes
- Supports multiple language pairs
- Easy to install and use via pipx
- Simple CLI interface

## Prerequisites

- Python 3.8 or later
- OpenAI Python client library 1.88.0 or later
- pipx installed ([installation guide](https://pipxproject.github.io/pipx/installation/))
- An OpenAI API key (set via the `OPENAI_API_KEY` environment variable)

## Language customization

The app is language-adaptive via two constants in the code:

- `LEARNER_LANGUAGE`: defines the target language to be practiced.
- `FEEDBACK_LANGUAGE`: defines the language used for feedback explanations.

You can modify these constants in the source code to switch between different language combinations.

Example: For French learners getting feedback in English
```python
LEARNER_LANGUAGE = "French"
FEEDBACK_LANGUAGE = "English"
```

## Installation

```bash
pipx install .
```

## How to use

```bash
repeat-chat-ai [<scene>]
```
If no scene is provided, defaults to 'at a café'.

## Example

```terminal
> ./repeat_chat_ai.py 'on the phone'
scene: A customer calls a hotel to make a reservation
role A: A customer looking to book a room for a weekend stay.
role B: A hotel receptionist assisting with reservations.
--------
A: こんにちは、今週末の部屋を予約したいのですが。
--------
A: Hello, I would like to book a room for this weekend.
[press space to repeat, enter for next]>
--------
B: かしこまりました。ご宿泊の日程を教えていただけますか？
--------
B: Certainly, ma'am.
>
B: What dates will you be staying with us?
>
--------
A: 金曜日の夜から日曜日の朝まで部屋が必要です。
--------
A: I need a room from Friday night to Sunday morning.
>
```

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.

## Author

- [Kazuaki Oshiba](https://github.com/kazusanto)
