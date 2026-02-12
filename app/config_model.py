from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    gigachat_key: str
    hotkey: str
    prompt_path: Path
    env_path: Path
