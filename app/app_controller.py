import platform
import threading
import time

import pyperclip
import whisper
from PySide6 import QtCore
from dotenv import set_key
from pynput import keyboard

from app.config_model import AppConfig
from app.constants import DEFAULT_HOTKEY
from app.logging_utils import LOGGER
from app.processing_worker import ProcessingWorker
from app.recorder import Recorder
from app.runtime_utils import get_whisper_cache_dir, resolve_local_whisper_checkpoint


class AppController(QtCore.QObject):
    ui_error = QtCore.Signal(str)

    def __init__(self, config: AppConfig, window):
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
            self.window.set_start_model_loading()

            try:
                cache_dir = get_whisper_cache_dir()
                checkpoint = resolve_local_whisper_checkpoint("base", cache_dir)
                self.whisper_model = whisper.load_model(checkpoint)
            except Exception as e:
                self._report_error(f"Ошибка загрузки Whisper: {e}", with_trace=True)
            finally:
                self.window.set_idle()

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

    def _process_audio(self, audio):
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

                result = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to keystroke "v" using command down',
                    ],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.decode("utf-8"))
            else:
                controller = keyboard.Controller()
                modifier = keyboard.Key.ctrl
                with controller.pressed(modifier):
                    controller.press(keyboard.KeyCode.from_char("v"))
                    controller.release(keyboard.KeyCode.from_char("v"))
            time.sleep(0.1)
        except Exception:
            self._report_error("Текст скопирован, вставьте вручную Cmd/Ctrl+V")
        finally:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    @staticmethod
    def _humanize_hotkey(hotkey: str) -> str:
        return (
            hotkey.replace("<cmd>", "Cmd")
            .replace("<ctrl>", "Ctrl")
            .replace("<alt>", "Alt")
            .replace("<shift>", "Shift")
            .replace("+", "+")
            .replace("<", "")
            .replace(">", "")
        )

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
