"""Persisted settings (key/value JSON in the `settings` table) with a pydantic model."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .db import Database

OcrBackendName = Literal["auto", "rapidocr", "winocr", "tesseract"]
CaptureScope = Literal["active", "all"]  # active = only the monitor with the foreground window


class Settings(BaseModel):
    enabled: bool = True
    paused: bool = False
    private: bool = False
    interval_s: int = Field(5, ge=1, le=600)
    ocr_backend: OcrBackendName = "auto"
    ocr_language: str = Field("es", min_length=2, max_length=8)
    retention_days: int = Field(30, ge=0, le=3650)  # 0 = keep forever
    storage_cap_mb: int = Field(5000, ge=100, le=1_000_000)
    dedupe_threshold: int = Field(16, ge=0, le=5000)  # changed grid cells (384x216) that make a new frame
    image_max_width: int = Field(1280, ge=320, le=3840)
    thumb_max_width: int = Field(320, ge=64, le=1024)
    capture_scope: CaptureScope = "active"


class SettingsPatch(BaseModel):
    """Every field optional: the UI writes single fields immediately."""

    enabled: bool | None = None
    paused: bool | None = None
    private: bool | None = None
    interval_s: int | None = Field(None, ge=1, le=600)
    ocr_backend: OcrBackendName | None = None
    ocr_language: str | None = Field(None, min_length=2, max_length=8)
    retention_days: int | None = Field(None, ge=0, le=3650)
    storage_cap_mb: int | None = Field(None, ge=100, le=1_000_000)
    dedupe_threshold: int | None = Field(None, ge=0, le=5000)
    image_max_width: int | None = Field(None, ge=320, le=3840)
    thumb_max_width: int | None = Field(None, ge=64, le=1024)
    capture_scope: CaptureScope | None = None


class SettingsStore:
    def __init__(self, db: Database):
        self.db = db
        self._cache: Settings | None = None

    def get(self) -> Settings:
        if self._cache is not None:
            return self._cache
        with self.db.lock:
            rows = self.db.conn.execute("SELECT key, value FROM settings").fetchall()
        raw = {}
        for row in rows:
            try:
                raw[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                continue
        known = {k: v for k, v in raw.items() if k in Settings.model_fields}
        try:
            self._cache = Settings(**known)
        except ValueError:
            self._cache = Settings()
        return self._cache

    def update(self, patch: SettingsPatch | dict) -> Settings:
        data = patch.model_dump(exclude_none=True) if isinstance(patch, SettingsPatch) else dict(patch)
        merged = self.get().model_copy(update=data)
        merged = Settings.model_validate(merged.model_dump())
        with self.db.lock:
            self.db.conn.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, json.dumps(value)) for key, value in merged.model_dump().items()],
            )
        self._cache = merged
        return merged
