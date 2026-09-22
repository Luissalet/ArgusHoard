"""Cross-platform screen capture with `mss` (Windows, X11). Raises on headless Linux.

`mss` instances are not thread-safe and, on Windows, belong to the thread that
created them: the recorder thread grabs, so the instance is thread-local and
created on first use. The constructor still opens one to fail early when there
is no display.
"""

from __future__ import annotations

import threading

from PIL import Image

from .base import CaptureBackend, Grab


class MssCapture(CaptureBackend):
    name = "mss"

    def __init__(self):
        import mss  # imported lazily: it touches the display on construction

        self._mss_module = mss
        self._local = threading.local()
        self._instances: list = []
        self._instance()  # probe: raises when capture is impossible here

    def _instance(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = self._mss_module.mss()
            self._local.sct = sct
            self._instances.append(sct)
        return sct

    def grab(self, all_monitors: bool = True) -> list[Grab]:
        sct = self._instance()
        monitors = sct.monitors  # [0] = virtual screen, [1..] = physical
        if len(monitors) <= 1:
            targets = [(1, monitors[0])]
        elif all_monitors:
            targets = list(enumerate(monitors))[1:]
        else:
            targets = [(1, monitors[1])]
        grabs = []
        for index, mon in targets:
            shot = sct.grab(mon)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            grabs.append(Grab(monitor=index, image=image, left=mon["left"], top=mon["top"]))
        return grabs

    def close(self) -> None:
        for sct in self._instances:
            try:
                sct.close()
            except Exception:
                pass
        self._instances.clear()
