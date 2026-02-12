import os
import sys
import threading
import tempfile
import time
import platform
import logging
import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv, set_key

from PySide6 import QtCore, QtGui, QtWidgets

import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper

from gigachat import GigaChat
from gigachat.models import Chat, Messages

import pyperclip
from pynput import keyboard

APP_NAME = "STT Desktop"
LOGGER = logging.getLogger("stt_desktop")

DEFAULT_HOTKEY = "<ctrl>+<cmd>+s"


@dataclass
class AppConfig:
    gigachat_key: str
    hotkey: str
    prompt_path: Path
    env_path: Path


def get_runtime_storage_paths() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        base_dir = Path.home() / ".stt-desktop"
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        # IDE/console mode: keep files in project root.
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

    candidates = []
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
        candidates.extend(
            [
                Path(meipass) / "ffmpeg",
                Path(meipass) / "ffmpeg.exe",
            ]
        )

    exe_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            exe_dir / "ffmpeg",
            exe_dir / "ffmpeg.exe",
        ]
    )

    ffmpeg_path = next((p for p in candidates if p.exists()), None)
    if not ffmpeg_path:
        return

    os.environ["FFMPEG_BINARY"] = str(ffmpeg_path)
    os.environ["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg_path)
    current_path = os.environ.get("PATH", "")
    ffmpeg_dir = str(ffmpeg_path.parent)
    if ffmpeg_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path


def get_home_app_dir() -> Path:
    app_dir = Path.home() / ".stt-desktop"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_runtime_app_dir() -> Path:
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
            # Keep app running even if a log file path is not writable.
            pass

    LOGGER.info("Logging initialized")


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


class Recorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self.samplerate = samplerate
        self.channels = channels
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._recording = False

    def start(self):
        if self._recording:
            return
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if not self._recording:
            return None
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)
        return audio

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass
        if not self._recording:
            return
        with self._lock:
            self._frames.append(indata.copy())


class ProcessingWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, audio: np.ndarray, config: AppConfig, whisper_model):
        super().__init__()
        self.audio = audio
        self.config = config
        self.whisper_model = whisper_model

    def run(self):
        try:
            text = self._transcribe(self.audio)
            if not text.strip():
                self.error.emit("Не удалось распознать речь (пустой результат)")
                return
            prompt = self._load_prompt()
            final_text = self._process_text(prompt, text)
            self.finished.emit(final_text)
        except Exception as e:
            self.error.emit(str(e))

    def _transcribe(self, audio: np.ndarray) -> str:
        waveform = np.asarray(audio, dtype=np.float32)
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        waveform = np.ascontiguousarray(waveform.squeeze())

        if waveform.size == 0:
            raise RuntimeError("Пустая аудиозапись")

        rms = float(np.sqrt(np.mean(np.square(waveform))))
        if rms < 1e-4:
            raise RuntimeError("Слишком тихий сигнал (проверьте микрофон и права доступа)")

        if rms < 0.01:
            gain = min(20.0, 0.03 / (rms + 1e-8))
            waveform = np.clip(waveform * gain, -1.0, 1.0)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        sf.write(path, waveform, 16000)
        result = self.whisper_model.transcribe(
            path,
            language="ru",
            task="transcribe",
            temperature=0.0,
            fp16=False,
        )
        try:
            os.unlink(path)
        except OSError:
            pass
        text = (result.get("text") or "").strip()
        if text:
            return text

        segments = result.get("segments") or []
        seg_text = " ".join((seg.get("text") or "").strip() for seg in segments).strip()
        return seg_text

    def _load_prompt(self) -> str:
        if self.config.prompt_path.exists():
            return self.config.prompt_path.read_text(encoding="utf-8").strip()
        return "Сделай текст красивым и грамотным."

    def _process_text(self, prompt: str, text: str) -> str:
        with GigaChat(credentials=self.config.gigachat_key, verify_ssl_certs=False) as giga:
            chat = Chat(
                messages=[
                    Messages(role="system", content=prompt),
                    Messages(role="user", content=text),
                ]
            )
            response = giga.chat(chat)
            print(response.choices[0].message.content.strip())
            return response.choices[0].message.content.strip()


class MainWindow(QtWidgets.QWidget):
    start_stop = QtCore.Signal()
    apply_settings = QtCore.Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(680, 500)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        self.tabs = QtWidgets.QTabWidget()

        self.recording_page = QtWidgets.QWidget()
        recording_layout = QtWidgets.QVBoxLayout(self.recording_page)

        self.status_label = QtWidgets.QLabel("Готов к записи")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

        self.action_button = QtWidgets.QPushButton("Начать запись")
        self.action_button.setFixedHeight(60)
        self.action_button.clicked.connect(self.start_stop.emit)

        self.hint_label = QtWidgets.QLabel("Горячая клавиша: Ctrl+Cmd+S")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)

        self.error_box = QtWidgets.QPlainTextEdit()
        self.error_box.setReadOnly(True)
        self.error_box.setPlaceholderText("Ошибки будут отображаться здесь")
        self.error_box.setFixedHeight(90)

        recording_layout.addStretch(1)
        recording_layout.addWidget(self.status_label)
        recording_layout.addSpacing(20)
        recording_layout.addWidget(self.action_button)
        recording_layout.addSpacing(12)
        recording_layout.addWidget(self.hint_label)
        recording_layout.addSpacing(10)
        recording_layout.addWidget(self.error_box)
        recording_layout.addStretch(2)

        self.settings_page = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(self.settings_page)

        self.hotkey_input = QtWidgets.QLineEdit()
        self.hotkey_input.setPlaceholderText("<ctrl>+<cmd>+s")

        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setPlaceholderText("GigaChat API key")

        self.prompt_input = QtWidgets.QPlainTextEdit()
        self.prompt_input.setPlaceholderText("Системный промпт для обработки текста...")
        self.prompt_input.setMinimumHeight(220)

        self.settings_status_label = QtWidgets.QLabel("")
        self.settings_status_label.setAlignment(QtCore.Qt.AlignLeft)

        self.apply_button = QtWidgets.QPushButton("Применить")
        self.apply_button.setFixedHeight(46)
        self.apply_button.clicked.connect(self._emit_apply_settings)

        form = QtWidgets.QFormLayout()
        form.addRow("Горячая клавиша", self.hotkey_input)
        form.addRow("API ключ GigaChat", self.api_key_input)
        form.addRow("Промпт", self.prompt_input)

        settings_layout.addLayout(form)
        settings_layout.addWidget(self.apply_button)
        settings_layout.addWidget(self.settings_status_label)
        settings_layout.addStretch(1)

        self.tabs.addTab(self.recording_page, "Запись")
        self.tabs.addTab(self.settings_page, "Настройки")

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.addWidget(self.tabs)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f172a, stop:1 #1f2937); color: #e5e7eb; }
            QLabel { font-size: 16px; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 12px; }
            QTabBar::tab { background: #1e293b; color: #cbd5e1; padding: 10px 16px; margin-right: 6px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #334155; color: #f8fafc; }
            QLineEdit, QPlainTextEdit { background: #111827; border: 1px solid #374151; border-radius: 10px; padding: 10px; color: #f3f4f6; }
            QPushButton { background: #22c55e; color: #0b111e; font-size: 18px; border: none; border-radius: 14px; padding: 12px; }
            QPushButton:hover { background: #16a34a; }
            QPushButton:pressed { background: #15803d; }
            """
        )

    def set_recording(self, is_recording: bool):
        if is_recording:
            self.status_label.setText("Идет запись…")
            self.action_button.setText("Остановить запись")
        else:
            self.status_label.setText("Готов к записи")
            self.action_button.setText("Начать запись")

    def set_processing(self):
        self.status_label.setText("Обрабатываю текст…")
        self.action_button.setText("Подождите…")
        self.action_button.setEnabled(False)

    def set_idle(self):
        self.action_button.setEnabled(True)
        self.set_recording(False)

    def set_settings(self, hotkey: str, api_key: str, prompt: str):
        self.hotkey_input.setText(hotkey)
        self.api_key_input.setText(api_key)
        self.prompt_input.setPlainText(prompt)

    def set_settings_status(self, text: str, ok: bool):
        color = "#86efac" if ok else "#fca5a5"
        self.settings_status_label.setStyleSheet(f"color: {color};")
        self.settings_status_label.setText(text)

    def _emit_apply_settings(self):
        self.apply_settings.emit(
            self.hotkey_input.text().strip(),
            self.api_key_input.text().strip(),
            self.prompt_input.toPlainText().strip(),
        )

    def set_error_text(self, text: str):
        self.error_box.setPlainText(text)

    def clear_error_text(self):
        self.error_box.clear()


class AppController(QtCore.QObject):
    ui_error = QtCore.Signal(str)

    def __init__(self, config: AppConfig, window: MainWindow):
        super().__init__()
        self.config = config
        self.window = window
        self.recorder = Recorder()
        self.is_recording = False
        self.is_processing = False
        self.is_audio_processing = False
        self.whisper_model = None
        self._hotkey_listener = None

        self.window.start_stop.connect(self.toggle_recording)
        self.window.apply_settings.connect(self.save_settings)
        self.ui_error.connect(self._apply_error_to_ui)

    def start(self):
        self._start_hotkey()
        self._load_whisper_async()

    def _load_whisper_async(self):
        def _load():
            try:
                cache_dir = get_whisper_cache_dir()
                checkpoint = resolve_local_whisper_checkpoint("base", cache_dir)
                self.whisper_model = whisper.load_model(checkpoint)
            except Exception as e:
                self._report_error(f"Ошибка загрузки Whisper: {e}", with_trace=True)
        t = threading.Thread(target=_load, daemon=True)
        t.start()

    def _start_hotkey(self):
        hotkey = self.config.hotkey or DEFAULT_HOTKEY
        self.window.hint_label.setText(f"Горячая клавиша: {self._humanize_hotkey(hotkey)}")
        try:
            if self._hotkey_listener is not None:
                self._hotkey_listener.stop()
            self._hotkey_listener = keyboard.GlobalHotKeys({hotkey: self.toggle_recording})
            self._hotkey_listener.start()
        except Exception as e:
            self._report_error(f"Ошибка hotkey: {e}", with_trace=True)

    def toggle_recording(self):
        if self.is_processing:
            return
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        try:
            self.recorder.start()
            self.is_recording = True
            self.window.set_recording(True)
            self.window.clear_error_text()
        except Exception as e:
            self._report_error(f"Ошибка записи: {e}", with_trace=True)

    def _stop_recording(self):
        audio = self.recorder.stop()
        self.is_recording = False
        if audio is None:
            self.window.set_idle()
            return
        if not self.config.gigachat_key:
            self._report_error("Укажите API ключ GigaChat в настройках")
            self.window.set_idle()
            return
        if self.whisper_model is None:
            self._report_error("Модель загружается или не загружена. Проверьте лог ошибок.")
            self.window.set_idle()
            return
        self.is_processing = True
        self.window.set_processing()
        self._process_audio(audio)

    def _process_audio(self, audio: np.ndarray):

        if self.is_audio_processing:
            print("Already processing")
            return
        self.is_audio_processing = True
        self.thread = QtCore.QThread()
        self.worker = ProcessingWorker(audio, self.config, self.whisper_model)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_processed)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _on_processed(self, text: str):
        self._paste_text(text)
        self.is_processing = False
        self.is_audio_processing = False
        self.window.set_idle()
        self.window.clear_error_text()
        self.thread.quit()

    def _on_error(self, msg: str):
        self.is_processing = False
        self.is_audio_processing = False
        self._report_error(f"Ошибка: {msg}")
        self.window.action_button.setEnabled(True)
        self.window.set_idle()
        self.thread.quit()

    def _paste_text(self, text: str):
        previous = pyperclip.paste()

        try:
            print(text)
            pyperclip.copy(text)
            time.sleep(0.2)

            if platform.system() == "Darwin":
                import subprocess
                result = subprocess.run([
                    'osascript', '-e',
                    'tell application "System Events" to keystroke "v" using command down'
                ], capture_output=True, timeout=5)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.decode('utf-8'))
            else:
                controller = keyboard.Controller()
                modifier = keyboard.Key.ctrl
                with controller.pressed(modifier):
                    controller.press(keyboard.KeyCode.from_char('v'))
                    controller.release(keyboard.KeyCode.from_char('v'))
            time.sleep(0.1)
        except Exception as e:
            self._report_error("Текст скопирован, вставьте вручную Cmd/Ctrl+V")
        finally:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    @staticmethod
    def _humanize_hotkey(hotkey: str) -> str:
        return hotkey.replace("<cmd>", "Cmd").replace("<ctrl>", "Ctrl").replace("<alt>", "Alt").replace("<shift>", "Shift").replace("+", "+").replace("<", "").replace(">", "")

    def save_settings(self, hotkey: str, api_key: str, prompt: str):
        if not hotkey:
            hotkey = DEFAULT_HOTKEY
        if not prompt:
            prompt = "Сделай текст красивым и грамотным."

        try:
            old_hotkey = self.config.hotkey
            self.config.hotkey = hotkey
            self.config.gigachat_key = api_key

            env_path = self.config.env_path
            env_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.prompt_path.parent.mkdir(parents=True, exist_ok=True)
            if not env_path.exists():
                env_path.write_text("", encoding="utf-8")

            set_key(str(env_path), "HOTKEY", hotkey)
            set_key(str(env_path), "GIGACHAT_API_KEY", api_key)
            set_key(str(env_path), "PROMPT_PATH", "prompt.md")

            self.config.prompt_path.write_text(prompt, encoding="utf-8")

            self.window.hint_label.setText(f"Горячая клавиша: {self._humanize_hotkey(hotkey)}")
            if hotkey != old_hotkey:
                self.window.set_settings_status(
                    "Настройки сохранены. Новая горячая клавиша применится после перезапуска приложения.",
                    True,
                )
            else:
                self.window.set_settings_status("Настройки сохранены", True)
        except Exception as e:
            self.window.set_settings_status(f"Ошибка сохранения: {e}", False)
            self._report_error(f"Ошибка сохранения: {e}", with_trace=True)

    def _report_error(self, message: str, with_trace: bool = False):
        self.ui_error.emit(message)
        if with_trace:
            LOGGER.exception(message)
        else:
            LOGGER.error(message)

    def _apply_error_to_ui(self, message: str):
        self.window.status_label.setText(message)
        self.window.set_error_text(message)


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


def main():
    configure_error_logging()
    configure_bundled_ffmpeg()

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = resolve_app_icon_path()
    app_icon = QtGui.QIcon(str(icon_path)) if icon_path else app.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
    app.setWindowIcon(app_icon)
    app.setApplicationDisplayName(APP_NAME)

    window = MainWindow()
    window.setWindowIcon(app_icon)

    try:
        config = load_config()
    except Exception as e:
        LOGGER.exception("Configuration load failed")
        QtWidgets.QMessageBox.critical(window, APP_NAME, str(e))
        return

    controller = AppController(config, window)
    default_prompt = "Сделай текст красивым и грамотным."
    if config.prompt_path.exists():
        default_prompt = config.prompt_path.read_text(encoding="utf-8").strip() or default_prompt
    window.set_settings(config.hotkey or DEFAULT_HOTKEY, config.gigachat_key, default_prompt)
    controller.start()

    tray = QtWidgets.QSystemTrayIcon(app_icon, window)
    menu = QtWidgets.QMenu()
    show_action = menu.addAction("Открыть")
    show_action.triggered.connect(window.show)
    toggle_action = menu.addAction("Старт/Стоп запись")
    toggle_action.triggered.connect(controller.toggle_recording)
    quit_action = menu.addAction("Выход")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip(APP_NAME)
    tray.show()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
