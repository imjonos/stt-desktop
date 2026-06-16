import platform
import threading


class PynputHotkeyListener:
    def __init__(self, hotkey: str, callback):
        from pynput import keyboard

        self._listener = keyboard.GlobalHotKeys({hotkey: callback})

    def start(self):
        self._listener.start()

    def wait(self):
        self._listener.wait()

    def stop(self):
        self._listener.stop()

    def join(self, timeout=None):
        self._listener.join(timeout=timeout)


class WindowsHotkeyListener:
    _HOTKEY_ID = 1
    _WM_HOTKEY = 0x0312
    _WM_QUIT = 0x0012
    _PM_NOREMOVE = 0x0000
    _MOD_ALT = 0x0001
    _MOD_CONTROL = 0x0002
    _MOD_SHIFT = 0x0004
    _MOD_WIN = 0x0008
    _MOD_NOREPEAT = 0x4000

    def __init__(self, hotkey: str, callback):
        self.hotkey = hotkey
        self.callback = callback
        self._modifiers, self._vk = _parse_windows_hotkey(hotkey)
        self._ready = threading.Event()
        self._thread_id = 0
        self._error = None
        self._thread = threading.Thread(
            target=self._run,
            name="stt-win32-hotkey",
            daemon=True,
        )

    def start(self):
        self._thread.start()

    def wait(self):
        if not self._ready.wait(timeout=3):
            raise RuntimeError("Timed out while registering Windows hotkey")
        if self._error is not None:
            raise self._error

    def stop(self):
        if self._thread_id:
            ctypes, wintypes, _MSG = _windows_api_types()
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(
                wintypes.DWORD(self._thread_id),
                self._WM_QUIT,
                wintypes.WPARAM(0),
                wintypes.LPARAM(0),
            )

    def join(self, timeout=None):
        self._thread.join(timeout=timeout)

    def _run(self):
        ctypes, wintypes, _MSG = _windows_api_types()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(_MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(_MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        self._thread_id = int(kernel32.GetCurrentThreadId())
        message = _MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, self._PM_NOREMOVE)

        modifiers = self._modifiers | self._MOD_NOREPEAT
        if not user32.RegisterHotKey(None, self._HOTKEY_ID, modifiers, self._vk):
            error_code = ctypes.get_last_error()
            self._error = ctypes.WinError(error_code)
            self._ready.set()
            return

        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0):
                if message.message == self._WM_HOTKEY and message.wParam == self._HOTKEY_ID:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, self._HOTKEY_ID)


def _windows_api_types():
    import ctypes
    from ctypes import wintypes

    class POINT(ctypes.Structure):
        _fields_ = [
            ("x", wintypes.LONG),
            ("y", wintypes.LONG),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", POINT),
        ]

    return ctypes, wintypes, MSG


def create_hotkey_listener(hotkey: str, callback):
    if platform.system() == "Windows":
        return WindowsHotkeyListener(hotkey, callback)
    return PynputHotkeyListener(hotkey, callback)


def _parse_windows_hotkey(hotkey: str) -> tuple[int, int]:
    modifiers = 0
    key = None
    for raw_part in hotkey.split("+"):
        part = raw_part.strip().lower()
        if part.startswith("<") and part.endswith(">"):
            part = part[1:-1]
        if part in {"ctrl", "control"}:
            modifiers |= WindowsHotkeyListener._MOD_CONTROL
        elif part == "alt":
            modifiers |= WindowsHotkeyListener._MOD_ALT
        elif part == "shift":
            modifiers |= WindowsHotkeyListener._MOD_SHIFT
        elif part in {"cmd", "win", "windows", "super"}:
            modifiers |= WindowsHotkeyListener._MOD_WIN
        elif part:
            if key is not None:
                raise ValueError(f"Hotkey must contain one non-modifier key: {hotkey}")
            key = part

    if key is None:
        raise ValueError(f"Hotkey must contain a non-modifier key: {hotkey}")
    return modifiers, _parse_windows_vk(key, hotkey)


def _parse_windows_vk(key: str, hotkey: str) -> int:
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    aliases = {
        "space": 0x20,
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "esc": 0x1B,
        "escape": 0x1B,
    }
    if key in aliases:
        return aliases[key]
    raise ValueError(f"Unsupported Windows hotkey key in {hotkey}: {key}")
