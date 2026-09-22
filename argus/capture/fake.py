"""Fake backends for tests and demos: scripted fixture scenes instead of the real screen."""

from __future__ import annotations

import itertools

from .base import CaptureBackend, Grab, WindowBackend, WindowInfo
from .fixtures import DEFAULT_SCENES, FixtureScene


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
    """Grabs the script's current scene (the window backend advances the script)."""

    name = "fake"

    def __init__(self, script: FakeScript):
        self.script = script

    def grab(self, all_monitors: bool = True) -> list[Grab]:
        scene = self.script.current
        return [Grab(monitor=1, image=scene.render().copy())]


class FakeWindow(WindowBackend):
    """Queried first on every tick (also on excluded ones), so it advances the script."""

    name = "fake"

    def __init__(self, script: FakeScript):
        self.script = script

    def active(self) -> WindowInfo:
        scene = self.script.advance()
        return WindowInfo(title=scene.title, app=scene.app, pid=4242, rect=(0, 0, scene.size[0], scene.size[1]))


class NullWindow(WindowBackend):
    """Used when no window backend exists for the platform (e.g. X11 without tooling)."""

    name = "none"

    def active(self) -> WindowInfo:
        return WindowInfo()


def make_fake_backends(scenes: list[FixtureScene] | None = None, loop: bool = True) -> tuple[FakeCapture, FakeWindow]:
    script = FakeScript(scenes, loop)
    return FakeCapture(script), FakeWindow(script)
