import os
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.config_model import AppConfig
from app.constants import DEFAULT_GIGACHAT_MODEL, DEFAULT_HOTKEY


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


def load_whisper_model(model_name: str, cache_dir: Path):
    import whisper

    model_candidate = Path(model_name)
    if model_candidate.is_file():
        return whisper.load_model(str(model_candidate))

    if model_name in whisper._MODELS:
        return whisper.load_model(model_name, download_root=str(cache_dir))

    raise RuntimeError(
        f"Unknown Whisper model '{model_name}'. Use known name or local checkpoint path."
    )


def load_config() -> AppConfig:
    env_path, default_prompt_path = get_runtime_storage_paths()
    load_dotenv(dotenv_path=env_path, override=True)

    key = os.getenv("GIGACHAT_API_KEY", "").strip()
    gigachat_model = os.getenv("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL).strip() or DEFAULT_GIGACHAT_MODEL
    hotkey = os.getenv("HOTKEY", DEFAULT_HOTKEY).strip()
    whisper_model = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    prompt_path_value = os.getenv("PROMPT_PATH", "prompt.md").strip()
    prompt_path = Path(prompt_path_value)
    if not prompt_path.is_absolute():
        prompt_path = env_path.parent / prompt_path
    if not prompt_path_value:
        prompt_path = default_prompt_path

    return AppConfig(
        gigachat_key=key,
        gigachat_model=gigachat_model,
        hotkey=hotkey,
        whisper_model=whisper_model,
        prompt_path=prompt_path,
        env_path=env_path,
    )
