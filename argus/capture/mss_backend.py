"""Cross-platform screen capture with `mss` (Windows, X11). Raises on headless Linux.

`mss` instances are not thread-safe and, on Windows, belong to the thread that
created them: the recorder thread grabs, so the instance is thread-local and
created on first use. The constructor still opens one to fail early when there
is no display.
"""

from __future__ import annotations

import threading

from PIL import Image

from .base import CaptureBackend, Grab, Monitor


class MssCapture(CaptureBackend):
    name = "mss"

    def __init__(self):
        import mss  # imported lazily: it touches the display on construction

        self._factory = getattr(mss, "MSS", None) or mss.mss  # `mss.mss` is deprecated in 10.x
        self._local = threading.local()
        self._instances: list = []
        self._instance()  # probe: raises when capture is impossible here

    def _instance(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = self._factory()
            self._local.sct = sct
            self._instances.append(sct)
        return sct

    def monitors(self) -> list[Monitor]:
        raw = self._instance().monitors  # [0] = virtual screen, [1..] = physical
        physical = raw[1:] if len(raw) > 1 else raw
        return [
            Monitor(index=i, left=m["left"], top=m["top"], width=m["width"], height=m["height"], primary=(m["left"] == 0 and m["top"] == 0))
            for i, m in enumerate(physical, start=1)
        ]

    def grab(self, monitors: list[int] | None = None) -> list[Grab]:
        sct = self._instance()
        raw = sct.monitors
        physical = raw[1:] if len(raw) > 1 else raw
        wanted = set(monitors) if monitors else None
        grabs = []
        for index, mon in enumerate(physical, start=1):
            if wanted is not None and index not in wanted:
                continue
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
