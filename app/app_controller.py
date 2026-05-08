import json
import platform
import subprocess
import threading
import time

import pyperclip
from PySide6 import QtCore
from dotenv import set_key

from app.config_model import AppConfig, PromptMode
from app.constants import DEFAULT_GIGACHAT_MODEL
from app.logging_utils import LOGGER
from app.runtime_utils import get_default_hotkey, get_whisper_cache_dir, load_whisper_model


class AppController(QtCore.QObject):
    ui_error = QtCore.Signal(str)
    model_loading = QtCore.Signal(str)
    model_ready = QtCore.Signal()
    toggle_requested = QtCore.Signal()

    def __init__(self, config: AppConfig, window):
        super().__init__()
        self.config = config
        self.window = window
        self.recorder = None
        self.is_recording = False
        self.is_processing = False
        self.is_audio_processing = False
        self.whisper_model = None
        self._hotkey_listener = None
        self._target_app_bundle_id = None

        self.window.start_stop.connect(self.toggle_recording)
        self.window.hiding_to_tray.connect(self._on_window_hidden_to_tray)
        self.window.apply_settings.connect(self.save_settings)
        self.ui_error.connect(self._apply_error_to_ui)
        self.model_loading.connect(self.window.set_start_model_loading)
        self.model_ready.connect(self.window.set_idle)
        self.toggle_requested.connect(self.toggle_recording)

    def shutdown(self):
        self._stop_hotkey()
        self._cancel_recording("shutdown")
        thread = getattr(self, "thread", None)
        try:
            thread_is_running = thread is not None and thread.isRunning()
        except RuntimeError:
            thread_is_running = False
        if thread_is_running:
            thread.quit()
            thread.wait(1500)

    def start(self):
        self._start_hotkey()
        self._load_whisper_async()

    def _load_whisper_async(self):
        def _load():
            model_name = self.config.whisper_model or "base"
            self.model_loading.emit(model_name)

            try:
                cache_dir = get_whisper_cache_dir()
                self.whisper_model = load_whisper_model(model_name, cache_dir)
                self.model_ready.emit()
            except Exception as e:
                self._report_error(f"Ошибка загрузки Whisper: {e}", with_trace=True)

        t = threading.Thread(target=_load, daemon=True)
        t.start()

    def _stop_hotkey(self, listener=None):
        listener = listener or self._hotkey_listener
        if listener is None:
            return

        if listener is self._hotkey_listener:
            self._hotkey_listener = None

        try:
            listener.stop()
            listener.join(timeout=1)
        except RuntimeError:
            pass
        except Exception as e:
            LOGGER.exception("Hotkey listener stop failed: %s", e)

    def _start_hotkey(self, hotkey: str | None = None) -> bool:
        from pynput import keyboard

        hotkey = hotkey or self.config.hotkey or get_default_hotkey()
        try:
            new_listener = keyboard.GlobalHotKeys({hotkey: self.toggle_requested.emit})
            new_listener.start()
        except Exception as e:
            self._report_error(f"Ошибка hotkey: {e}", with_trace=True)
            return False

        old_listener = self._hotkey_listener
        self._hotkey_listener = new_listener
        self.window.hint_label.setText(f"Горячая клавиша: {self._humanize_hotkey(hotkey)}")
        if old_listener is not None:
            self._stop_hotkey(old_listener)
        return True

    def toggle_recording(self):
        if self.is_processing:
            return
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _on_window_hidden_to_tray(self):
        if self.is_recording:
            self._cancel_recording("window hidden to tray")
            self.window.set_idle()

    def _start_recording(self):
        try:
            self._target_app_bundle_id = self._get_frontmost_app_bundle_id()
            if self.recorder is None:
                from app.recorder import Recorder

                self.recorder = Recorder()
            self.recorder.start()
            self.is_recording = True
            self.window.set_recording(True)
            self.window.clear_error_text()
        except Exception as e:
            self._report_error(f"Ошибка записи: {e}", with_trace=True)

    def _stop_recording(self):
        if self.recorder is None:
            self.is_recording = False
            self.window.set_idle()
            return
        try:
            audio = self.recorder.stop()
        except Exception as e:
            self.is_recording = False
            self._report_error(f"Ошибка остановки записи: {e}", with_trace=True)
            self.window.set_idle()
            return
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

    def _cancel_recording(self, reason: str):
        if not self.is_recording or self.recorder is None:
            return
        try:
            self.recorder.stop()
            LOGGER.info("Recording cancelled: %s", reason)
        except Exception:
            LOGGER.exception("Recorder stop failed during %s", reason)
        finally:
            self.is_recording = False

    def _process_audio(self, audio):
        if self.is_audio_processing:
            print("Already processing")
            return
        from app.processing_worker import ProcessingWorker

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
        try:
            if self._paste_text(text):
                self.window.clear_error_text()
        finally:
            self.is_processing = False
            self.is_audio_processing = False
            self.window.set_idle()
            self.thread.quit()

    def _on_error(self, msg: str):
        self.is_processing = False
        self.is_audio_processing = False
        self._report_error(f"Ошибка: {msg}")
        self.window.action_button.setEnabled(True)
        self.window.set_idle()
        self.thread.quit()

    def _paste_text(self, text: str):
        try:
            LOGGER.info("Pasting processed text, length=%s", len(text))
            pyperclip.copy(text)
            time.sleep(0.35)

            if platform.system() == "Darwin":
                self._activate_target_app()
                time.sleep(0.2)
                self._paste_on_macos()
            else:
                self._paste_with_keyboard_controller(use_cmd=False)
            time.sleep(0.25)
            return True
        except Exception as e:
            LOGGER.exception("Auto paste failed")
            self._report_error(f"Текст распознан и оставлен в буфере обмена. Вставьте вручную Cmd/Ctrl+V. Детали: {e}")
            return False

    @staticmethod
    def _get_frontmost_app_bundle_id() -> str | None:
        if platform.system() != "Darwin":
            return None

        script = (
            'tell application "System Events" to get bundle identifier of '
            "first application process whose frontmost is true"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
        except Exception:
            return None

        bundle_id = result.stdout.strip()
        if bundle_id in {"com.sttdesktop.app", "org.python.python", "com.apple.Terminal"}:
            return None
        return bundle_id or None

    def _activate_target_app(self):
        if not self._target_app_bundle_id:
            return

        subprocess.run(
            ["osascript", "-e", f'tell application id "{self._target_app_bundle_id}" to activate'],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )

    @classmethod
    def _paste_on_macos(cls):
        errors = []
        paste_methods = (
            cls._paste_with_system_events,
            lambda: cls._paste_with_keyboard_controller(use_cmd=True),
        )
        for paste_method in paste_methods:
            try:
                paste_method()
                return
            except Exception as e:
                errors.append(e)
                LOGGER.warning("Paste method failed: %s", e)
                time.sleep(0.1)
        raise RuntimeError("; ".join(str(error) for error in errors))

    @staticmethod
    def _paste_with_system_events():
        script = 'tell application "System Events" to keystroke "v" using command down'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )

    @staticmethod
    def _paste_with_keyboard_controller(use_cmd: bool):
        from pynput import keyboard

        controller = keyboard.Controller()
        modifier = keyboard.Key.cmd if use_cmd else keyboard.Key.ctrl
        with controller.pressed(modifier):
            controller.press(keyboard.KeyCode.from_char("v"))
            controller.release(keyboard.KeyCode.from_char("v"))

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

    def save_settings(
        self,
        hotkey: str,
        api_key: str,
        gigachat_model: str,
        whisper_model: str,
        prompt_modes_data,
        active_prompt_mode_id: str,
    ):
        if not hotkey:
            hotkey = get_default_hotkey()
        if not gigachat_model:
            gigachat_model = DEFAULT_GIGACHAT_MODEL
        if not whisper_model:
            whisper_model = "base"

        try:
            old_hotkey = self.config.hotkey
            old_whisper_model = self.config.whisper_model
            prompt_modes = self._normalize_prompt_modes(prompt_modes_data)
            if not any(mode.id == active_prompt_mode_id for mode in prompt_modes):
                active_prompt_mode_id = prompt_modes[0].id
            self.config.hotkey = hotkey
            self.config.gigachat_key = api_key
            self.config.gigachat_model = gigachat_model
            self.config.whisper_model = whisper_model
            self.config.prompt_modes = prompt_modes
            self.config.active_prompt_mode_id = active_prompt_mode_id

            env_path = self.config.env_path
            env_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.prompt_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.prompt_modes_path.parent.mkdir(parents=True, exist_ok=True)
            if not env_path.exists():
                env_path.write_text("", encoding="utf-8")

            set_key(str(env_path), "HOTKEY", hotkey)
            set_key(str(env_path), "GIGACHAT_API_KEY", api_key)
            set_key(str(env_path), "GIGACHAT_MODEL", gigachat_model)
            set_key(str(env_path), "WHISPER_MODEL", whisper_model)
            set_key(str(env_path), "PROMPT_PATH", "prompt.md")
            set_key(str(env_path), "PROMPT_MODES_PATH", "prompt_modes.json")
            set_key(str(env_path), "ACTIVE_PROMPT_MODE", active_prompt_mode_id)

            self.config.prompt_modes_path.write_text(
                json.dumps(
                    [
                        {"id": mode.id, "title": mode.title, "prompt": mode.prompt}
                        for mode in prompt_modes
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            active_mode = self._get_active_prompt_mode()
            if active_mode:
                self.config.prompt_path.write_text(active_mode.prompt, encoding="utf-8")
                self.window.set_active_mode(active_mode.title)

            restart_changes = []
            if hotkey != old_hotkey:
                if not self._start_hotkey(hotkey):
                    self.config.hotkey = old_hotkey
                    set_key(str(env_path), "HOTKEY", old_hotkey)
                    self.window.set_settings_status("Не удалось применить новую горячую клавишу", False)
                    return
            if whisper_model != old_whisper_model:
                restart_changes.append("модель")
            if restart_changes:
                self.window.set_settings_status(
                    f"Настройки сохранены. После перезапуска применится: {', '.join(restart_changes)}.",
                    True,
                )
            else:
                self.window.set_settings_status("Настройки сохранены", True)
        except Exception as e:
            self.window.set_settings_status(f"Ошибка сохранения: {e}", False)
            self._report_error(f"Ошибка сохранения: {e}", with_trace=True)

    @staticmethod
    def _normalize_prompt_modes(prompt_modes_data) -> list[PromptMode]:
        modes = []
        seen = set()
        for item in prompt_modes_data or []:
            mode_id = str(item.get("id", "")).strip()
            title = str(item.get("title", "")).strip()
            prompt = str(item.get("prompt", "")).strip()
            if not title or not prompt:
                continue
            if not mode_id:
                mode_id = AppController._slugify_mode_id(title)
            original_mode_id = mode_id
            counter = 2
            while mode_id in seen:
                mode_id = f"{original_mode_id}_{counter}"
                counter += 1
            seen.add(mode_id)
            modes.append(PromptMode(id=mode_id, title=title, prompt=prompt))

        if modes:
            return modes
        return [PromptMode(id="polish", title="Красивый текст", prompt="Сделай текст красивым и грамотным.")]

    @staticmethod
    def _slugify_mode_id(title: str) -> str:
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug or "mode"

    def _get_active_prompt_mode(self) -> PromptMode | None:
        for mode in self.config.prompt_modes:
            if mode.id == self.config.active_prompt_mode_id:
                return mode
        return self.config.prompt_modes[0] if self.config.prompt_modes else None

    def _report_error(self, message: str, with_trace: bool = False):
        self.ui_error.emit(message)
        if with_trace:
            LOGGER.exception(message)
        else:
            LOGGER.error(message)

    def _apply_error_to_ui(self, message: str):
        self.window.status_label.setText("Ошибка")
        self.window.status_detail_label.setText(message)
        self.window.status_dot.setStyleSheet("background: #fb7185; border-radius: 7px;")
        self.window.set_error_text(message)
