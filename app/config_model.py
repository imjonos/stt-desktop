from dataclasses import dataclass
from pathlib import Path


@dataclass
class PromptMode:
    id: str
    title: str
    prompt: str


@dataclass
class AppConfig:
    gigachat_key: str
    gigachat_model: str
    hotkey: str
    whisper_model: str
    prompt_modes: list[PromptMode]
    active_prompt_mode_id: str
    prompt_path: Path
    prompt_modes_path: Path
    env_path: Path
