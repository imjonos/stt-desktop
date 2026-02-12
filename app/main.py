import os
import sys
import threading
import tempfile
import time
import platform
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

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

DEFAULT_HOTKEY = "<ctrl>+<cmd>+s"
DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompt.md"
TRAY_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "tray.png"


@dataclass
class AppConfig:
    gigachat_key: str
    hotkey: str
    prompt_path: Path


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
                self.error.emit("Empty transcript")
                return
            prompt = self._load_prompt()
            final_text = self._process_text(prompt, text)
            self.finished.emit(final_text)
        except Exception as e:
            self.error.emit(str(e))

    def _transcribe(self, audio: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        sf.write(path, audio, 16000)
        result = self.whisper_model.transcribe(path, language="ru")
        try:
            os.unlink(path)
        except OSError:
            pass
        return result.get("text", "")

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

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(520, 320)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        self.status_label = QtWidgets.QLabel("Готов к записи")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

        self.action_button = QtWidgets.QPushButton("Начать запись")
        self.action_button.setFixedHeight(60)
        self.action_button.clicked.connect(self.start_stop.emit)

        self.hint_label = QtWidgets.QLabel("Горячая клавиша: Ctrl+Cmd+S")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addSpacing(20)
        layout.addWidget(self.action_button)
        layout.addSpacing(12)
        layout.addWidget(self.hint_label)
        layout.addStretch(2)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f172a, stop:1 #1f2937); color: #e5e7eb; }
            QLabel { font-size: 16px; }
            QPushButton { background: #22c55e; color: #0b111e; font-size: 20px; border: none; border-radius: 14px; padding: 12px; }
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


class AppController(QtCore.QObject):
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

    def start(self):
        self._start_hotkey()
        self._load_whisper_async()

    def _load_whisper_async(self):
        def _load():
            self.whisper_model = whisper.load_model("base")
        t = threading.Thread(target=_load, daemon=True)
        t.start()

    def _start_hotkey(self):
        hotkey = self.config.hotkey or DEFAULT_HOTKEY
        self.window.hint_label.setText(f"Горячая клавиша: {self._humanize_hotkey(hotkey)}")
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({hotkey: self.toggle_recording})
            self._hotkey_listener.start()
        except Exception as e:
            self.window.status_label.setText(f"Ошибка hotkey: {e}")

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
        except Exception as e:
            self.window.status_label.setText(f"Ошибка записи: {e}")

    def _stop_recording(self):
        audio = self.recorder.stop()
        self.is_recording = False
        if audio is None:
            self.window.set_idle()
            return
        if self.whisper_model is None:
            self.window.status_label.setText("Модель загружается, попробуйте еще раз")
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
        self.thread.quit()

    def _on_error(self, msg: str):
        self.is_processing = False
        self.is_audio_processing = False
        self.window.status_label.setText(f"Ошибка: {msg}")
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
            self.window.status_label.setText("✅ Текст скопирован! Нажмите Ctrl+V")
        finally:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    @staticmethod
    def _humanize_hotkey(hotkey: str) -> str:
        return hotkey.replace("<cmd>", "Cmd").replace("<ctrl>", "Ctrl").replace("<alt>", "Alt").replace("<shift>", "Shift").replace("+", "+").replace("<", "").replace(">", "")


def load_config() -> AppConfig:
    load_dotenv()
    key = os.getenv("GIGACHAT_API_KEY", "").strip()
    hotkey = os.getenv("HOTKEY", DEFAULT_HOTKEY).strip()
    prompt_path = Path(os.getenv("PROMPT_PATH", str(DEFAULT_PROMPT_PATH)))
    if not key:
        raise RuntimeError("GIGACHAT_API_KEY is missing in .env")
    return AppConfig(gigachat_key=key, hotkey=hotkey, prompt_path=prompt_path)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app_icon = QtGui.QIcon(str(TRAY_ICON_PATH))
    app.setWindowIcon(app_icon)
    app.setApplicationDisplayName(APP_NAME)

    window = MainWindow()
    window.setWindowIcon(app_icon)

    try:
        config = load_config()
    except Exception as e:
        QtWidgets.QMessageBox.critical(window, APP_NAME, str(e))
        return

    controller = AppController(config, window)
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
    main()
