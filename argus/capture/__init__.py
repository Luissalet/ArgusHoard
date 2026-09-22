"""Backend selection by platform and configuration. Never crashes on import."""

from __future__ import annotations

import sys

from .base import Backends, CaptureBackend, Grab, WindowBackend, WindowInfo
from .fake import NullWindow, make_fake_backends

__all__ = ["Backends", "CaptureBackend", "Grab", "WindowBackend", "WindowInfo", "select_backends"]


class UnavailableCapture(CaptureBackend):
    """Placeholder that explains why capture is impossible instead of crashing."""

    name = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def grab(self, all_monitors: bool = True) -> list[Grab]:
        raise RuntimeError(self.reason)


def select_backends(capture: str = "auto", window: str = "auto") -> Backends:
    notes: list[str] = []
    if capture == "fake" or window == "fake":
        fake_capture, fake_window = make_fake_backends()
        return Backends(fake_capture if capture in ("fake", "auto") else _real_capture(capture, notes), fake_window, notes)
    cap = _real_capture(capture, notes)
    win = _real_window(window, notes)
    return Backends(cap, win, notes)


def _real_capture(kind: str, notes: list[str]) -> CaptureBackend:
    if kind == "none":
        return UnavailableCapture("Capture disabled by ARGUS_CAPTURE=none.")
    try:
        from .mss_backend import MssCapture

        return MssCapture()
    except Exception as error:  # headless Linux, missing display, missing module
        notes.append(f"mss unavailable: {error}")
        return UnavailableCapture(f"Screen capture unavailable: {error}")


def _real_window(kind: str, notes: list[str]) -> WindowBackend:
    if kind == "none":
        return NullWindow()
    if sys.platform == "win32" and kind in ("auto", "windows"):
        try:
            from .windows import WindowsActiveWindow

            return WindowsActiveWindow()
        except Exception as error:
            notes.append(f"windows window backend unavailable: {error}")
    elif kind == "windows":
        notes.append("windows window backend requested on a non-Windows platform")
    else:
        notes.append("no active-window backend for this platform; frames are stored without app/title")
    return NullWindow()
