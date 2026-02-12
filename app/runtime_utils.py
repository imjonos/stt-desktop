import os
import platform
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
import whisper

from app.config_model import AppConfig
from app.constants import DEFAULT_HOTKEY


def get_runtime_storage_paths() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        base_dir = Path.home() / ".stt-desktop"
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = Path(__file__).resolve().parent.parent

    return base_dir / ".env", base_dir / "prompt.md"


def get_resource_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_app_icon_path() -> Path | None:
    base_dir = get_resource_base_dir()
    assets_dir = base_dir / "assets"
    system = platform.system()

    if system == "Darwin":
        candidates = [assets_dir / "icon.icns", assets_dir / "tray.png"]
    elif system == "Windows":
        candidates = [assets_dir / "icon.ico", assets_dir / "tray.png"]
    else:
        candidates = [assets_dir / "tray.png", assets_dir / "icon.ico"]

    for path in candidates:
        if path.exists():
            return path
    return None


def configure_bundled_ffmpeg():
    if not getattr(sys, "frozen", False):
        return

    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend([Path(meipass) / "ffmpeg", Path(meipass) / "ffmpeg.exe"])

    exe_dir = Path(sys.executable).resolve().parent
    candidates.extend([exe_dir / "ffmpeg", exe_dir / "ffmpeg.exe"])

    ffmpeg_path = next((p for p in candidates if p.exists()), None)
    if not ffmpeg_path:
        return

    os.environ["FFMPEG_BINARY"] = str(ffmpeg_path)
    os.environ["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg_path)
    current_path = os.environ.get("PATH", "")
    ffmpeg_dir = str(ffmpeg_path.parent)
    if ffmpeg_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path


def get_whisper_cache_dir() -> Path:
    cache_dir = Path.home() / ".stt-desktop" / "whisper-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def resolve_local_whisper_checkpoint(model_name: str, cache_dir: Path) -> str:
    model_candidate = Path(model_name)
    if model_candidate.is_file():
        return str(model_candidate)

    if model_name in whisper._MODELS:
        model_url = whisper._MODELS[model_name]
        filename = Path(urlparse(model_url).path).name
        checkpoint = cache_dir / filename
        if checkpoint.is_file():
            return str(checkpoint)
        raise RuntimeError(
            f"Whisper model '{model_name}' not found in cache: {checkpoint}"
        )

    raise RuntimeError(
        f"Unknown Whisper model '{model_name}'. Use known name or local checkpoint path."
    )


def load_config() -> AppConfig:
    env_path, default_prompt_path = get_runtime_storage_paths()
    load_dotenv(dotenv_path=env_path, override=True)

    key = os.getenv("GIGACHAT_API_KEY", "").strip()
    hotkey = os.getenv("HOTKEY", DEFAULT_HOTKEY).strip()
    prompt_path_value = os.getenv("PROMPT_PATH", "prompt.md").strip()
    prompt_path = Path(prompt_path_value)
    if not prompt_path.is_absolute():
        prompt_path = env_path.parent / prompt_path
    if not prompt_path_value:
        prompt_path = default_prompt_path

    return AppConfig(gigachat_key=key, hotkey=hotkey, prompt_path=prompt_path, env_path=env_path)
