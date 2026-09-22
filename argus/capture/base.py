"""Backend interfaces for screen capture and active-window lookup."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image


@dataclass(frozen=True)
class Monitor:
    index: int  # 1-based, stable for the session
    left: int
    top: int
    width: int
    height: int
    primary: bool = False

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.left + self.width and self.top <= y < self.top + self.height


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

    def monitor_index(self, monitors: list[Monitor]) -> int | None:
        """Which monitor contains the window's centre point (None if unknown)."""
        if not self.rect:
            return None
        cx = (self.rect[0] + self.rect[2]) // 2
        cy = (self.rect[1] + self.rect[3]) // 2
        for monitor in monitors:
            if monitor.contains(cx, cy):
                return monitor.index
        return None


def primary_index(monitors: list[Monitor]) -> int:
    for monitor in monitors:
        if monitor.primary:
            return monitor.index
    return monitors[0].index if monitors else 1


class CaptureBackend:
    name = "base"

    def monitors(self) -> list[Monitor]:  # pragma: no cover - interface
        raise NotImplementedError

    def grab(self, monitors: list[int] | None = None) -> list[Grab]:  # pragma: no cover - interface
        """Capture the given monitor indexes (None = every monitor)."""
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
