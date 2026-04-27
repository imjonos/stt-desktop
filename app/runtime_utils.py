import os
import platform
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

from app.config_model import AppConfig, PromptMode
from app.constants import DEFAULT_GIGACHAT_MODEL, DEFAULT_HOTKEY


DEFAULT_POLISH_PROMPT = "Сделай текст красивым и грамотным."
DEFAULT_UNIX_PROMPT = (
    "Преобразуй распознанную речь в одну Unix/Linux shell-команду. "
    "Верни только команду без Markdown, пояснений и кавычек вокруг всего ответа. "
    "Если запрос неоднозначен, выбери самый безопасный и типичный вариант."
)


def get_runtime_storage_paths() -> tuple[Path, Path, Path]:
    if getattr(sys, "frozen", False):
        base_dir = Path.home() / ".stt-desktop"
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = Path(__file__).resolve().parent.parent

    return base_dir / ".env", base_dir / "prompt.md", base_dir / "prompt_modes.json"


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

    try:
        subprocess.run(
            [str(ffmpeg_path), "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=True,
        )
    except Exception:
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


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_ssl_verify_error(error: Exception) -> bool:
    reason = getattr(error, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(error)


@contextmanager
def _without_ssl_verification():
    original_urlopen = urllib.request.urlopen
    context = ssl._create_unverified_context()

    def urlopen_no_verify(url, *args, **kwargs):
        kwargs.setdefault("context", context)
        return original_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = urlopen_no_verify
    try:
        yield
    finally:
        urllib.request.urlopen = original_urlopen


def load_whisper_model(model_name: str, cache_dir: Path):
    import whisper

    model_candidate = Path(model_name)
    if model_candidate.is_file():
        return whisper.load_model(str(model_candidate))

    if model_name in whisper._MODELS:
        if _env_flag("WHISPER_SSL_NO_VERIFY"):
            with _without_ssl_verification():
                return whisper.load_model(model_name, download_root=str(cache_dir))

        try:
            return whisper.load_model(model_name, download_root=str(cache_dir))
        except urllib.error.URLError as e:
            if not _is_ssl_verify_error(e):
                raise
            with _without_ssl_verification():
                return whisper.load_model(model_name, download_root=str(cache_dir))

    raise RuntimeError(
        f"Unknown Whisper model '{model_name}'. Use known name or local checkpoint path."
    )


def _load_prompt_modes(modes_path: Path, legacy_prompt_path: Path) -> list[PromptMode]:
    if modes_path.exists():
        with modes_path.open("r", encoding="utf-8") as f:
            raw_modes = json.load(f)
        modes = []
        for item in raw_modes if isinstance(raw_modes, list) else []:
            mode_id = str(item.get("id", "")).strip()
            title = str(item.get("title", "")).strip()
            prompt = str(item.get("prompt", "")).strip()
            if mode_id and title and prompt:
                modes.append(PromptMode(id=mode_id, title=title, prompt=prompt))
        if modes:
            return modes

    legacy_prompt = DEFAULT_POLISH_PROMPT
    if legacy_prompt_path.exists():
        legacy_prompt = legacy_prompt_path.read_text(encoding="utf-8").strip() or legacy_prompt

    return [
        PromptMode(id="polish", title="Красивый текст", prompt=legacy_prompt),
        PromptMode(id="unix_command", title="Unix-команда", prompt=DEFAULT_UNIX_PROMPT),
    ]


def load_config() -> AppConfig:
    env_path, default_prompt_path, default_prompt_modes_path = get_runtime_storage_paths()
    load_dotenv(dotenv_path=env_path, override=True)

    key = os.getenv("GIGACHAT_API_KEY", "").strip()
    gigachat_model = os.getenv("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL).strip() or DEFAULT_GIGACHAT_MODEL
    hotkey = os.getenv("HOTKEY", DEFAULT_HOTKEY).strip()
    whisper_model = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    active_prompt_mode_id = os.getenv("ACTIVE_PROMPT_MODE", "polish").strip() or "polish"
    prompt_path_value = os.getenv("PROMPT_PATH", "prompt.md").strip()
    prompt_modes_path_value = os.getenv("PROMPT_MODES_PATH", "prompt_modes.json").strip()
    prompt_path = Path(prompt_path_value)
    if not prompt_path.is_absolute():
        prompt_path = env_path.parent / prompt_path
    if not prompt_path_value:
        prompt_path = default_prompt_path
    prompt_modes_path = Path(prompt_modes_path_value)
    if not prompt_modes_path.is_absolute():
        prompt_modes_path = env_path.parent / prompt_modes_path
    if not prompt_modes_path_value:
        prompt_modes_path = default_prompt_modes_path

    prompt_modes = _load_prompt_modes(prompt_modes_path, prompt_path)
    if not any(mode.id == active_prompt_mode_id for mode in prompt_modes):
        active_prompt_mode_id = prompt_modes[0].id

    return AppConfig(
        gigachat_key=key,
        gigachat_model=gigachat_model,
        hotkey=hotkey,
        whisper_model=whisper_model,
        prompt_modes=prompt_modes,
        active_prompt_mode_id=active_prompt_mode_id,
        prompt_path=prompt_path,
        prompt_modes_path=prompt_modes_path,
        env_path=env_path,
    )
