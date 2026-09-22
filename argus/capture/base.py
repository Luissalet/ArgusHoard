"""Backend interfaces for screen capture and active-window lookup."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image


@dataclass
class Grab:
    monitor: int  # 1-based monitor index
    image: Image.Image
    left: int = 0
    top: int = 0


@dataclass
class WindowInfo:
    title: str = ""
    app: str = ""  # process name without extension, e.g. "notepad"
    pid: int | None = None
    rect: tuple[int, int, int, int] | None = None  # left, top, right, bottom in screen coords

    def monitor_index(self, grabs: list[Grab]) -> int | None:
        """Which grab contains the window's centre point (None if unknown)."""
        if not self.rect:
            return None
        cx = (self.rect[0] + self.rect[2]) // 2
        cy = (self.rect[1] + self.rect[3]) // 2
        for grab in grabs:
            if grab.left <= cx < grab.left + grab.image.width and grab.top <= cy < grab.top + grab.image.height:
                return grab.monitor
        return None


class CaptureBackend:
    name = "base"

    def grab(self, all_monitors: bool = True) -> list[Grab]:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        return None


class WindowBackend:
    name = "base"

    def active(self) -> WindowInfo:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class Backends:
    capture: CaptureBackend
    window: WindowBackend
    notes: list[str] = field(default_factory=list)
