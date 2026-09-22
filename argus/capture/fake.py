"""Fake backends for tests and demos: scripted fixture scenes instead of the real screen."""

from __future__ import annotations

import itertools

from .base import CaptureBackend, Grab, Monitor, WindowBackend, WindowInfo
from .fixtures import DEFAULT_SCENES, FAKE_MONITORS, FixtureScene, render_idle_monitor


class FakeScript:
    """Shared cursor so the capture and window backends stay in sync per tick."""

    def __init__(self, scenes: list[FixtureScene] | None = None, loop: bool = True):
        self.scenes = scenes or DEFAULT_SCENES
        self.loop = loop
        self._ticks = [scene for scene in self.scenes for _ in range(scene.repeat)]
        self._iter = itertools.cycle(self._ticks) if loop else iter(self._ticks)
        self.current: FixtureScene = self._ticks[0]
        self.ticks_served = 0

    def advance(self) -> FixtureScene:
        try:
            self.current = next(self._iter)
        except StopIteration:
            pass  # stay on the last scene when not looping
        self.ticks_served += 1
        return self.current


class FakeCapture(CaptureBackend):
    """Grabs the script's current scene (the window backend advances the script).

    The scene appears on its own monitor; every other monitor shows a static desktop.
    """

    name = "fake"

    def __init__(self, script: FakeScript, monitors: list[Monitor] | None = None):
        self.script = script
        self._monitors = monitors or [Monitor(*m) for m in FAKE_MONITORS]
        self._idle = {m.index: render_idle_monitor(m.index) for m in self._monitors}
        self.grab_calls: list[list[int] | None] = []  # what was requested, for tests

    def monitors(self) -> list[Monitor]:
        return list(self._monitors)

    def grab(self, monitors: list[int] | None = None) -> list[Grab]:
        self.grab_calls.append(monitors)
        scene = self.script.current
        wanted = set(monitors) if monitors else None
        grabs = []
        for m in self._monitors:
            if wanted is not None and m.index not in wanted:
                continue
            image = scene.render() if scene.monitor == m.index else self._idle[m.index]
            grabs.append(Grab(monitor=m.index, image=image.copy(), left=m.left, top=m.top))
        return grabs


class FakeWindow(WindowBackend):
    """Queried first on every tick (also on excluded ones), so it advances the script."""

    name = "fake"

    def __init__(self, script: FakeScript):
        self.script = script

    def active(self) -> WindowInfo:
        scene = self.script.advance()
        offset = next((m for m in FAKE_MONITORS if m[0] == scene.monitor), FAKE_MONITORS[0])
        left, top = offset[1] + 40, offset[2] + 40
        return WindowInfo(title=scene.title, app=scene.app, pid=4242, rect=(left, top, left + scene.size[0] - 80, top + scene.size[1] - 80))


class NullWindow(WindowBackend):
    """Used when no window backend exists for the platform (e.g. X11 without tooling)."""

    name = "none"

    def active(self) -> WindowInfo:
        return WindowInfo()


def make_fake_backends(scenes: list[FixtureScene] | None = None, loop: bool = True) -> tuple[FakeCapture, FakeWindow]:
    script = FakeScript(scenes, loop)
    return FakeCapture(script), FakeWindow(script)
