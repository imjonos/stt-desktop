from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    gigachat_key: str
    gigachat_model: str
    hotkey: str
    whisper_model: str
    prompt_path: Path
    env_path: Path
