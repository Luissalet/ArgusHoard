"""Retention and storage-cap housekeeping, plus explicit range deletion."""

from __future__ import annotations

import logging
import time

from .settings import SettingsStore
from .store import FrameStore

log = logging.getLogger("argus.janitor")


class Janitor:
    def __init__(self, frames: FrameStore, settings: SettingsStore):
        self.frames = frames
        self.settings = settings
        self.last_run: float | None = None
        self.last_deleted = 0

    def run(self, now: float | None = None) -> dict:
        now = now or time.time()
        s = self.settings.get()
        deleted_by_age = deleted_by_cap = 0
        if s.retention_days > 0:
            cutoff = now - s.retention_days * 86400
            deleted_by_age = self.frames.delete_frames(self.frames.frame_ids_older_than(cutoff))
        cap_bytes = s.storage_cap_mb * 1024 * 1024
        deleted_by_cap = self.frames.delete_frames(self.frames.oldest_frames_over_cap(cap_bytes))
        self.last_run = now
        self.last_deleted = deleted_by_age + deleted_by_cap
        if self.last_deleted:
            log.info("janitor removed %s frames (age %s, cap %s)", self.last_deleted, deleted_by_age, deleted_by_cap)
        return {"deleted_by_age": deleted_by_age, "deleted_by_cap": deleted_by_cap}

    def delete_range(self, start: float | None, end: float | None) -> int:
        return self.frames.delete_frames(self.frames.frame_ids_between(start, end))
