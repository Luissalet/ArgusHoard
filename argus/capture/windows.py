"""Active window on Windows via ctypes (user32) + psutil. Import-safe on other platforms."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .base import WindowBackend, WindowInfo

IS_WINDOWS = sys.platform == "win32"


class WindowsActiveWindow(WindowBackend):
    name = "windows"

    def __init__(self):
        if not IS_WINDOWS:
            raise RuntimeError("The Windows window backend only works on Windows.")
        import psutil

        self._psutil = psutil
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        # Explicit signatures: without them ctypes truncates 64-bit handles to int.
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetForegroundWindow.argtypes = []
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32 = user32
        self._names: dict[int, str] = {}

    def _process_name(self, pid: int) -> str:
        if pid in self._names:
            return self._names[pid]
        try:
            name = self._psutil.Process(pid).name()
        except Exception:
            name = ""
        if name.lower().endswith(".exe"):
            name = name[:-4]
        if len(self._names) > 512:
            self._names.clear()
        self._names[pid] = name
        return name

    def active(self) -> WindowInfo:
        user32 = self._user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return WindowInfo()
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        got_rect = user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return WindowInfo(
            title=buffer.value,
            app=self._process_name(pid.value) if pid.value else "",
            pid=pid.value or None,
            rect=(rect.left, rect.top, rect.right, rect.bottom) if got_rect else None,
        )
