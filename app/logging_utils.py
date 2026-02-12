import logging
from pathlib import Path

LOGGER = logging.getLogger("stt_desktop")


def get_home_app_dir() -> Path:
    app_dir = Path.home() / ".stt-desktop"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_runtime_app_dir() -> Path:
    import sys
    from pathlib import Path

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configure_error_logging():
    if LOGGER.handlers:
        return

    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    log_paths = [
        get_home_app_dir() / "app-errors.log",
        get_runtime_app_dir() / "app-errors.log",
    ]

    for log_path in log_paths:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setLevel(logging.INFO)
            handler.setFormatter(formatter)
            LOGGER.addHandler(handler)
        except Exception:
            pass

    LOGGER.info("Logging initialized")
