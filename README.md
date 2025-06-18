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
- PyGame library 2.6.1 or later
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

```terminal
repeat-chat-ai [<scene>]
```
If no scene is provided, defaults to 'at a café'.

## Example

```terminal
> ./repeat_chat_ai.py 'on the phone'
scene: Making an appointment on the phone
role A: A customer trying to book a haircut appointment.
role B: A receptionist at a hair salon.
A: Hello, I would like to make an appointment for a haircut.
→ こんにちは、ヘアカットの予約をしたいのですが。
[press space to repeat, enter for next]>
A: Do you have any openings this week?
→ 今週の空きはありますか？
>
B: Hello! Yes, we do have some available slots.
→ こんにちは！はい、いくつか空いている時間があります。
>
B: What day were you thinking about?
→ 何曜日をお考えですか？
>
A: I was hoping for Thursday afternoon, if possible.
→ 木曜日の午後がいいのですが、可能でしょうか。
>
A: Around 3 PM, maybe?
→ 3時ごろでお願いします。
>
B: Let me check.
→ 確認しますね。
>
B: Yes, we have a 3 PM appointment available on Thursday.
→ はい、木曜日の3時に空きがあります。
>
```

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.

## Author

- [Kazuaki Oshiba](https://github.com/kazusanto)
