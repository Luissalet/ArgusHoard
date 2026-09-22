"""Wiring of database, stores, backends, recorder, OCR worker and janitor."""

from __future__ import annotations

import logging
import secrets
import shutil
import time

from . import __version__
from .capture import select_backends
from .config import Config
from .db import Database
from .janitor import Janitor
from .ocr import ocr_availability
from .queries import Queries
from .recorder import Recorder
from .settings import SettingsPatch, SettingsStore
from .store import ExclusionStore, FrameStore
from .timeparse import iso_local
from .worker import OcrWorker

log = logging.getLogger("argus")


def write_token(config: Config) -> str:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    config.token_path.write_text(token, encoding="utf-8")
    try:
        config.token_path.chmod(0o600)
    except OSError:
        pass
    return token


class Services:
    def __init__(self, config: Config):
        self.config = config
        self.started_at = time.time()
        config.data_dir.mkdir(parents=True, exist_ok=True)
        config.frames_dir.mkdir(parents=True, exist_ok=True)
        self.token = write_token(config)
        self.db = Database(config.db_path)
        self.settings = SettingsStore(self.db)
        self.frames = FrameStore(self.db, config.frames_dir)
        self.exclusions = ExclusionStore(self.db)
        self.queries = Queries(self.db)
        s = self.settings.get()
        self.backends = select_backends(config.capture_backend, config.window_backend)
        for note in self.backends.notes:
            log.info("capture: %s", note)
        self.ocr = OcrWorker(self.frames, s.ocr_backend, s.ocr_language)
        self.janitor = Janitor(self.frames, self.settings)
        self.recorder = Recorder(self.backends, self.settings, self.frames, self.exclusions, self.ocr, on_idle=self.janitor.run)

    # ---------- lifecycle ----------
    def start(self) -> None:
        self.ocr.start()
        if self.config.autostart:
            self.recorder.start()
        try:
            self.janitor.run()
        except Exception as error:  # pragma: no cover
            log.warning("initial housekeeping failed: %s", error)

    def stop(self) -> None:
        self.recorder.stop()
        self.ocr.stop()
        self.db.close()

    # ---------- settings ----------
    def update_settings(self, patch: SettingsPatch | dict):
        merged = self.settings.update(patch)
        self.ocr.reconfigure(merged.ocr_backend, merged.ocr_language)
        self.recorder.wake()
        return merged

    # ---------- status ----------
    def status(self) -> dict:
        s = self.settings.get()
        usage = self.frames.disk_usage()
        try:
            disk = shutil.disk_usage(self.config.data_dir)
            free = disk.free
        except OSError:
            free = None
        today = self.frames.today_stats()
        return {
            "service": "argus-hoard",
            "version": __version__,
            "state": self.recorder.state(),
            "enabled": s.enabled,
            "paused": s.paused,
            "private": s.private,
            "recorder_running": self.recorder.running(),
            "interval_s": s.interval_s,
            "queue_depth": self.ocr.depth,
            "ocr_backend": self.ocr.engine_name(),
            "ocr_requested": s.ocr_backend,
            "ocr_processed": self.ocr.processed,
            "ocr_last_ms": self.ocr.last_ms,
            "ocr_notes": self.ocr.notes,
            "capture_backend": self.backends.capture.name,
            "window_backend": self.backends.window.name,
            "capture_notes": self.backends.notes,
            "last_capture_at": iso_local(self.recorder.last_capture_at) if self.recorder.last_capture_at else None,
            "last_error": self.recorder.last_error or self.ocr.last_error,
            "frames_total": self.frames.frame_count(),
            "today": today,
            "disk_usage_bytes": usage,
            "disk_free_bytes": free,
            "storage_cap_mb": s.storage_cap_mb,
            "retention_days": s.retention_days,
            "data_dir": str(self.config.data_dir),
            "janitor_last_run": iso_local(self.janitor.last_run) if self.janitor.last_run else None,
            "ocr_available": ocr_availability(),
        }
