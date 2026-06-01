from dataclasses import dataclass
from pathlib import Path


@dataclass
class PromptMode:
    id: str
    title: str
    prompt: str


@dataclass
class AppConfig:
    # AI API настройки
    ai_provider: str  # "gigachat" или "openai"
    ai_api_key: str
    ai_model: str
    ai_base_url: str | None  # Для OpenAI-совместимых API

    # Legacy GigaChat поля для обратной совместимости
    gigachat_key: str
    gigachat_model: str

    hotkey: str
    whisper_model: str
    prompt_modes: list[PromptMode]
    active_prompt_mode_id: str
    prompt_path: Path
    prompt_modes_path: Path
    env_path: Path
