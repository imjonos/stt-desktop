import unittest
from unittest import mock

from app.hotkey_listener import (
    PynputHotkeyListener,
    WindowsHotkeyListener,
    _parse_windows_hotkey,
    create_hotkey_listener,
)


class HotkeyListenerTest(unittest.TestCase):
    def test_parse_windows_ctrl_alt_letter_hotkey(self):
        modifiers, vk = _parse_windows_hotkey("<ctrl>+<alt>+s")

        self.assertEqual(
            modifiers,
            WindowsHotkeyListener._MOD_CONTROL | WindowsHotkeyListener._MOD_ALT,
        )
        self.assertEqual(vk, ord("S"))

    def test_parse_windows_function_key_hotkey(self):
        modifiers, vk = _parse_windows_hotkey("<ctrl>+<shift>+f9")

        self.assertEqual(
            modifiers,
            WindowsHotkeyListener._MOD_CONTROL | WindowsHotkeyListener._MOD_SHIFT,
        )
        self.assertEqual(vk, 0x78)

    def test_factory_uses_windows_listener_only_on_windows(self):
        with mock.patch("app.hotkey_listener.platform.system", return_value="Windows"):
            listener = create_hotkey_listener("<ctrl>+<alt>+s", lambda: None)

        self.assertIsInstance(listener, WindowsHotkeyListener)

    def test_factory_keeps_pynput_listener_on_macos(self):
        with (
            mock.patch("app.hotkey_listener.platform.system", return_value="Darwin"),
            mock.patch.object(PynputHotkeyListener, "__init__", return_value=None) as init_listener,
        ):
            listener = create_hotkey_listener("<ctrl>+<cmd>+s", lambda: None)

        self.assertIsInstance(listener, PynputHotkeyListener)
        init_listener.assert_called_once()


if __name__ == "__main__":
    unittest.main()
