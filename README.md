# STT Desktop

STT Desktop is an alpha desktop app for dictation. Press a global hotkey, speak, and the app turns your voice into text, processes it with the selected prompt mode, and pastes the result into the active window.

The core idea is simple: dictate a Telegram message, email, or note in text mode, or describe what you want to do in a terminal and get a ready-to-paste shell command in command mode.

Cross-platform Python desktop app:
- Global hotkey for recording
- Local Whisper speech-to-text
- Text post-processing with AI (GigaChat, OpenAI, or any OpenAI-compatible API)
- Multiple prompt modes for different workflows
- Automatic paste into the active input field (Cmd+V / Ctrl+V)

## Quick Start

Use Python 3.11 (64-bit on Windows). This is the version used to test the
desktop runtime and PyInstaller build.

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. For IDE/console runs, create `.env` in the project root:
```bash
cp .env.example .env
```

3. Edit `.env` and set your AI provider and API key.

4. Run the app:
```bash
python -m app.main
```

## AI Providers

The app supports multiple AI providers for text post-processing. You can switch between them in the Settings tab.

### GigaChat (default)
- Select **GigaChat** in the provider dropdown
- Enter your GigaChat API key
- Choose a model: `GigaChat`, `GigaChat-Pro`, or `GigaChat-Max`

### OpenAI / Compatible APIs
- Select **OpenAI / Совместимый** in the provider dropdown
- Enter your API key
- Optionally set a **Base URL** if you use a custom or local endpoint (for example, Lamy, LM Studio, Ollama with OpenAI compatibility layer, or any other OpenAI-compatible service)
- Choose or type a model name (`gpt-4o-mini`, `gpt-4o`, `gpt-4`, `gpt-3.5-turbo`, or any custom model ID)

## Prompt Modes

The app supports multiple text-processing modes. Each mode is a separate system prompt for the AI that defines how recognized speech should be transformed before it is pasted.

Available by default:
- `Polished text` — improves dictated text, fixes mistakes, and makes the result clean and readable. Useful for Telegram, email, notes, and any input field where you need natural text.
- `Unix command` — turns a voice request into a shell command. Useful in a terminal: describe what you want to do, then paste the generated command into the command line.

In settings, you can choose the active mode, edit its name and prompt, delete modes you do not need, or add new modes for your own workflows.

## File Storage

For the packaged app (`.app` / `.exe`), the working directory is:
- `~/.stt-desktop/`

This directory contains:
- `~/.stt-desktop/.env` — app configuration
- `~/.stt-desktop/prompt.md` — current prompt, also editable manually
- `~/.stt-desktop/prompt_modes.json` — processing modes with names and prompts
- `~/.stt-desktop/whisper-cache/` — Whisper model cache
- `~/.stt-desktop/app-errors.log` — application error log

Notes:
- In IDE/console mode, `.env` and `prompt.md` are loaded from the project root.
- In the packaged app, `.env` and `prompt.md` are loaded from `~/.stt-desktop/`.

## `.env` Variables

### AI Settings
- `AI_PROVIDER` — AI provider: `gigachat` or `openai`
- `AI_API_KEY` — unified API key (used for both GigaChat and OpenAI-compatible APIs)
- `AI_MODEL` — model name, for example `GigaChat` or `gpt-4o-mini`
- `AI_BASE_URL` — optional base URL for OpenAI-compatible APIs (e.g., `https://api.openai.com/v1`)

### Legacy GigaChat Settings
- `GIGACHAT_API_KEY` — GigaChat API key (used as fallback if `AI_API_KEY` is not set)
- `GIGACHAT_MODEL` — GigaChat model for text post-processing, defaults to `GigaChat`

### App Settings
- `HOTKEY` — global hotkey in `pynput` format, for example `<ctrl>+<cmd>+s`
- `PROMPT_PATH` — path to `prompt.md`, usually `prompt.md`
- `PROMPT_MODES_PATH` — path to the prompt modes JSON file, usually `prompt_modes.json`
- `ACTIVE_PROMPT_MODE` — id of the active processing mode
- `WHISPER_MODEL` — Whisper model; `tiny` starts faster, `base` is more accurate and used by default
- `WHISPER_SSL_NO_VERIFY` — disables SSL verification when downloading Whisper models, useful in some corporate networks

## Permissions

macOS permissions for the packaged `.app`:
- `System Settings -> Privacy & Security -> Microphone`
- `System Settings -> Privacy & Security -> Accessibility`
- `System Settings -> Privacy & Security -> Input Monitoring`

Recording and automatic paste may not work without these permissions.

On Windows, use the default `<ctrl>+<alt>+s` hotkey. The app cannot send
`Ctrl+V` into a window running as Administrator when STT Desktop itself is
running without elevation. Runtime diagnostics are written to
`%USERPROFILE%\\.stt-desktop\\app-errors.log`.

## Build

```bash
python build.py
```

On macOS, the build uses a `.spec` file with plist settings and microphone permissions.
Build the Windows executable on Windows; PyInstaller does not cross-compile.
