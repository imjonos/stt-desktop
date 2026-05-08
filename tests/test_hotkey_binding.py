import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path


class FakeSignal:
    def __init__(self, *_args):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class FakeQObject:
    def __init__(self, *_args, **_kwargs):
        pass


qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QObject = FakeQObject
qtcore.Signal = FakeSignal
pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules.setdefault("PySide6", pyside6)
sys.modules.setdefault("PySide6.QtCore", qtcore)


class FakeApplication:
    current = None

    @staticmethod
    def instance():
        return FakeApplication.current


class FakeWidget:
    def __init__(self, *_args, **_kwargs):
        self.hidden = False
        self.super_close_called = False

    def hide(self):
        self.hidden = True

    def closeEvent(self, _event):
        self.super_close_called = True


qtwidgets = types.ModuleType("PySide6.QtWidgets")
qtwidgets.QApplication = FakeApplication
qtwidgets.QWidget = FakeWidget
pyside6.QtWidgets = qtwidgets
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)

pyperclip = types.ModuleType("pyperclip")
pyperclip.paste = lambda: ""
pyperclip.copy = lambda _text: None
sys.modules.setdefault("pyperclip", pyperclip)

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *_args, **_kwargs: None
dotenv.set_key = lambda *_args, **_kwargs: None
sys.modules.setdefault("dotenv", dotenv)


class FakeGlobalHotKeys:
    instances = []
    fail_for = set()

    def __init__(self, hotkeys):
        self.hotkey = next(iter(hotkeys))
        if self.hotkey in self.fail_for:
            raise ValueError(self.hotkey)
        self.callback = hotkeys[self.hotkey]
        self.started = False
        self.stopped = False
        self.join_timeout = None
        self.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        self.join_timeout = timeout


keyboard = types.ModuleType("pynput.keyboard")
keyboard.GlobalHotKeys = FakeGlobalHotKeys
pynput = types.ModuleType("pynput")
pynput.keyboard = keyboard
sys.modules.setdefault("pynput", pynput)
sys.modules.setdefault("pynput.keyboard", keyboard)

from app.app_controller import AppController
from app.config_model import AppConfig, PromptMode
from app.logging_utils import LOGGER
from app.main_window import MainWindow
from app.runtime_utils import get_default_hotkey

LOGGER.disabled = True


class FakeLabel:
    def __init__(self):
        self.text = ""
        self.style = ""

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.style = style


class FakeWindow:
    def __init__(self):
        self.start_stop = FakeSignal()
        self.hiding_to_tray = FakeSignal()
        self.apply_settings = FakeSignal()
        self.hint_label = FakeLabel()
        self.status_label = FakeLabel()
        self.status_detail_label = FakeLabel()
        self.status_dot = FakeLabel()
        self.status_text = None
        self.status_ok = None
        self.error_text = ""
        self.active_mode = ""

    def set_start_model_loading(self, *_args):
        pass

    def set_idle(self):
        pass

    def set_settings_status(self, text, ok):
        self.status_text = text
        self.status_ok = ok

    def set_error_text(self, text):
        self.error_text = text

    def set_active_mode(self, title):
        self.active_mode = title


class HotkeyBindingTest(unittest.TestCase):
    def setUp(self):
        FakeGlobalHotKeys.instances.clear()
        FakeGlobalHotKeys.fail_for.clear()
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.config = AppConfig(
            gigachat_key="old-key",
            gigachat_model="GigaChat",
            hotkey="<ctrl>+<cmd>+s",
            whisper_model="base",
            prompt_modes=[PromptMode(id="polish", title="Красивый текст", prompt="Prompt")],
            active_prompt_mode_id="polish",
            prompt_path=base / "prompt.md",
            prompt_modes_path=base / "prompt_modes.json",
            env_path=base / ".env",
        )
        self.window = FakeWindow()
        self.controller = AppController(self.config, self.window)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_rebinds_hotkey_immediately_and_stops_old_listener(self):
        self.assertTrue(self.controller._start_hotkey())
        old_listener = FakeGlobalHotKeys.instances[-1]

        modes = [{"id": "polish", "title": "Красивый текст", "prompt": "Prompt"}]
        self.controller.save_settings("<ctrl>+<alt>+x", "new-key", "GigaChat-Pro", "base", modes, "polish")
        new_listener = FakeGlobalHotKeys.instances[-1]

        self.assertIs(self.controller._hotkey_listener, new_listener)
        self.assertTrue(new_listener.started)
        self.assertTrue(old_listener.stopped)
        self.assertEqual(old_listener.join_timeout, 1)
        self.assertEqual(self.config.hotkey, "<ctrl>+<alt>+x")
        self.assertEqual(self.config.gigachat_model, "GigaChat-Pro")
        self.assertEqual(self.window.hint_label.text, "Горячая клавиша: Ctrl+Alt+x")
        self.assertEqual(self.window.status_text, "Настройки сохранены")
        self.assertTrue(self.window.status_ok)

    def test_failed_rebind_keeps_existing_listener_and_old_hotkey(self):
        self.assertTrue(self.controller._start_hotkey())
        old_listener = FakeGlobalHotKeys.instances[-1]
        FakeGlobalHotKeys.fail_for.add("bad-hotkey")

        modes = [{"id": "polish", "title": "Красивый текст", "prompt": "Prompt"}]
        self.controller.save_settings("bad-hotkey", "new-key", "GigaChat-Pro", "base", modes, "polish")

        self.assertIs(self.controller._hotkey_listener, old_listener)
        self.assertFalse(old_listener.stopped)
        self.assertEqual(self.config.hotkey, "<ctrl>+<cmd>+s")
        self.assertEqual(self.window.status_text, "Не удалось применить новую горячую клавишу")
        self.assertFalse(self.window.status_ok)

    def test_macos_paste_falls_back_to_keyboard_controller(self):
        with (
            mock.patch.object(AppController, "_paste_with_system_events", side_effect=RuntimeError("blocked")),
            mock.patch.object(AppController, "_paste_with_keyboard_controller") as keyboard_paste,
            mock.patch("app.app_controller.time.sleep"),
        ):
            AppController._paste_on_macos()

        keyboard_paste.assert_called_once_with(use_cmd=True)

    def test_hiding_to_tray_cancels_active_recording(self):
        recorder = mock.Mock()
        self.controller.recorder = recorder
        self.controller.is_recording = True

        self.controller._on_window_hidden_to_tray()

        recorder.stop.assert_called_once_with()
        self.assertFalse(self.controller.is_recording)

    def test_windows_default_hotkey_does_not_use_cmd(self):
        with mock.patch("app.runtime_utils.platform.system", return_value="Windows"):
            self.assertEqual(get_default_hotkey(), "<ctrl>+<alt>+s")


class FakeCloseEvent:
    def __init__(self):
        self.ignored = False

    def ignore(self):
        self.ignored = True


class MainWindowCloseTest(unittest.TestCase):
    def tearDown(self):
        FakeApplication.current = None

    def test_close_hides_window_to_tray_by_default(self):
        FakeApplication.current = types.SimpleNamespace(_stt_force_quit=False)
        window = MainWindow.__new__(MainWindow)
        FakeWidget.__init__(window)
        event = FakeCloseEvent()

        window.closeEvent(event)

        self.assertTrue(event.ignored)
        self.assertTrue(window.hidden)
        self.assertFalse(window.super_close_called)

    def test_close_allows_real_quit_when_requested(self):
        FakeApplication.current = types.SimpleNamespace(_stt_force_quit=True)
        window = MainWindow.__new__(MainWindow)
        FakeWidget.__init__(window)
        event = FakeCloseEvent()

        window.closeEvent(event)

        self.assertFalse(event.ignored)
        self.assertFalse(window.hidden)
        self.assertTrue(window.super_close_called)


if __name__ == "__main__":
    unittest.main()
