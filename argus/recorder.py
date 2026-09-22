"""The capture loop: one tick every `interval_s`, dedupe, exclusions, store, enqueue OCR."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from .capture import Backends
from .capture.base import primary_index
from .exclusions import first_match
from .images import dhash, is_near_duplicate, signature
from .settings import SettingsStore
from .store import ExclusionStore, FrameStore
from .worker import OcrWorker

log = logging.getLogger("argus.recorder")


@dataclass
class TickResult:
    stored: list[int] = field(default_factory=list)
    extended: list[int] = field(default_factory=list)
    hidden: bool = False
    skipped_reason: str | None = None
    monitors: list[int] = field(default_factory=list)  # monitors captured this tick
    active_monitor: int | None = None


class Recorder:
    def __init__(
        self,
        backends: Backends,
        settings: SettingsStore,
        frames: FrameStore,
        exclusions: ExclusionStore,
        ocr: OcrWorker,
        on_idle=None,
    ):
        self.backends = backends
        self.settings = settings
        self.frames = frames
        self.exclusions = exclusions
        self.ocr = ocr
        self.on_idle = on_idle  # periodic housekeeping hook (janitor)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_capture_at: float | None = None
        self.last_error: str | None = None
        self.last_tick: TickResult | None = None
        self.ticks = 0
        self.idle_since: float | None = None  # captured_at of the frame the active monitor keeps repeating
        self.active_monitor: int | None = None
        self._last_signature: dict[int, tuple[int, object]] = {}  # monitor -> (frame id, grid signature)

    # ---------- lifecycle ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="argus-recorder", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)
        self.backends.capture.close()

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def wake(self) -> None:
        """Called after a settings change so a new interval/pause applies at once."""
        self._wake.set()

    def state(self) -> str:
        s = self.settings.get()
        if not s.enabled:
            return "disabled"
        if s.private:
            return "private"
        if s.paused:
            return "paused"
        return "watching"

    # ---------- loop ----------
    def _run(self) -> None:
        last_idle = 0.0
        while not self._stop.is_set():
            settings = self.settings.get()
            started = time.monotonic()
            if self.state() != "watching":
                self.idle_since = None
            else:
                try:
                    self.tick()
                    self.last_error = None
                except Exception as error:
                    if str(error) != self.last_error:  # log once per distinct failure, not every tick
                        log.warning("capture failed: %s", error)
                    self.last_error = str(error)
            if self.on_idle and time.monotonic() - last_idle > 600:
                last_idle = time.monotonic()
                try:
                    self.on_idle()
                except Exception as error:  # never kill the loop
                    log.warning("housekeeping failed: %s", error)
            elapsed = time.monotonic() - started
            self._wake.wait(max(0.2, settings.interval_s - elapsed))
            self._wake.clear()

    def tick(self, now: float | None = None) -> TickResult:
        """One capture cycle; public so tests and the selftest can drive it synchronously."""
        now = float(int(now or time.time()))  # whole seconds: what the API/UI show is exact
        settings = self.settings.get()
        result = TickResult()
        self.ticks += 1
        window = self.backends.window.active()
        rule = first_match(self.exclusions.list(), window.app, window.title)
        if rule is not None:
            self.frames.record_tick(now, hidden=True)
            result.hidden = True
            result.skipped_reason = f"excluded by {rule.kind} rule {rule.pattern!r}"
            self.idle_since = None
            self.last_capture_at = now
            self.last_tick = result
            return result
        monitors = self.backends.capture.monitors()
        active_monitor = window.monitor_index(monitors)
        if active_monitor is None and monitors:
            active_monitor = primary_index(monitors)  # unknown window position: assume the primary
        wanted = None if settings.capture_scope == "all" or active_monitor is None else [active_monitor]
        grabs = self.backends.capture.grab(wanted)
        self.last_capture_at = now
        self.active_monitor = active_monitor
        result.active_monitor = active_monitor
        result.monitors = [g.monitor for g in grabs]
        for grab in grabs:
            on_this_monitor = active_monitor is None or active_monitor == grab.monitor
            app = window.app if on_this_monitor else ""
            title = window.title if on_this_monitor else ""
            current = signature(grab.image)
            previous = self.frames.last_frame(grab.monitor)
            remembered = self._last_signature.get(grab.monitor)
            recent = previous is not None and now - previous.until_at < 2 * settings.interval_s
            same_window = previous is not None and previous.window_title == title and previous.app == app
            previous_signature = remembered[1] if remembered and previous and remembered[0] == previous.id else None
            if recent and same_window and is_near_duplicate(previous_signature, current, settings.dedupe_threshold):
                self.frames.extend_frame(previous.id, now + settings.interval_s)
                result.extended.append(previous.id)
                if on_this_monitor:
                    self.idle_since = previous.captured_at  # nothing changed since that frame was stored
                continue
            if on_this_monitor:
                self.idle_since = None
            frame_id = self.frames.insert_frame(
                grab.image,
                captured_at=now,
                interval_s=settings.interval_s,
                monitor=grab.monitor,
                app=app,
                window_title=title,
                phash=dhash(grab.image),
                image_max_width=settings.image_max_width,
                thumb_max_width=settings.thumb_max_width,
            )
            self._last_signature[grab.monitor] = (frame_id, current)
            self.ocr.submit(frame_id, grab.image)
            result.stored.append(frame_id)
        self.frames.record_tick(now, hidden=False)
        self.last_tick = result
        return result
