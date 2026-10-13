"""Import existing screenshots through the ordinary frame store and OCR queue."""
from __future__ import annotations

import hashlib
from io import BytesIO
from datetime import datetime
import math
import os
from pathlib import Path
import time

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import images
from .hoard_link.agentkit import AppError
from .hoard_link.docs.imaging import dhash

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
FORMATS = {"PNG", "JPEG", "WEBP", "BMP"}


class ScreenImportArgs(BaseModel):
    paths: list[str] = Field(..., min_length=1, description="Existing screenshots or folders. Originals are read without modification.")
    recursive: bool = Field(False, description="Include nested folders when importing a folder.")
    app: str = Field("Archivo importado", description="Source label, not a claim that this app was active.")
    captured_at: str | None = Field(None, description="Known capture date/time. Omit to use the file modification date, explicitly labelled as such.")


class ScreenImportListArgs(BaseModel):
    limit: int = Field(60, ge=1, le=500)
    before: int | None = Field(None, ge=1, description="Continue at next_before from the previous page.")


def _timestamp(value):
    try:
        stamp = float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(value).timestamp()
    except (ValueError, TypeError, OverflowError):
        raise AppError("invalid_import_date", "The screenshot date must be finite and valid.") from None
    if stamp is None or not math.isfinite(stamp):
        raise AppError("invalid_import_date", "The screenshot date must be finite and valid.")
    return stamp


def import_image(svc, data: bytes, *, source: str, title: str, at: float, time_basis: str, app: str) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(BytesIO(data)) as original:
            if original.format not in FORMATS or getattr(original, "n_frames", 1) != 1:
                raise ValueError("Use a still PNG, JPEG, WebP or BMP screenshot.")
            original.load()
            image = ImageOps.exif_transpose(original).convert("RGB")
    except UnidentifiedImageError:
        raise ValueError("The file is not a readable screenshot.") from None
    with svc.db.lock:
        existing = svc.db.conn.execute("SELECT id FROM frames WHERE origin = 'import' AND source_path = ? AND source_sha256 = ?", (source, digest)).fetchone()
        if existing:
            return {"id": existing["id"], "source": source, "duplicate": True, "source_sha256": digest}
        frame_id = None
        svc.db.conn.execute("BEGIN")
        try:
            frame_id = svc.frames.insert_frame(image, captured_at=at, interval_s=0, monitor=0, app=app,
                                               window_title=title, phash=dhash(image), image_max_width=image.width)
            svc.db.conn.execute("UPDATE frames SET origin = 'import', source_path = ?, source_sha256 = ?, time_basis = ?, imported_at = ?, pinned = 1 WHERE id = ?",
                                (source, digest, time_basis, time.time(), frame_id))
            # The calendar includes stored imports, but capture statistics count only observed captures.
            svc.db.conn.execute("UPDATE daily_stats SET frames = frames - 1 WHERE day = (SELECT day FROM frames WHERE id = ?)", (frame_id,))
            svc.db.conn.execute("COMMIT")
        except BaseException:
            info = svc.frames.image_file(frame_id) if frame_id is not None else None
            svc.db.conn.execute("ROLLBACK")
            if info:
                images.remove_images(info[0], info[1])
            raise
    svc.ocr.submit(frame_id, image)
    return {"id": frame_id, "source": source, "duplicate": False, "source_sha256": digest,
            "time_basis": time_basis, "pinned": True, "ocr_status": "pending", "image_url": f"/api/frames/{frame_id}/image"}


def import_paths(svc, args: ScreenImportArgs) -> dict:
    results, errors = [], []
    given_at = _timestamp(args.captured_at) if args.captured_at else None
    entries = []
    for raw in args.paths:
        try:
            path = Path(raw).expanduser()
            if not path.exists():
                raise ValueError("File or folder not found.")
            if path.is_dir():
                files = sorted(p for p in (path.rglob("*") if args.recursive else path.iterdir()) if p.is_file() and p.suffix.lower() in EXTENSIONS)
                if not files:
                    raise ValueError("No supported screenshots found in this folder.")
                entries.extend(files)
            else:
                entries.append(path)
        except (OSError, ValueError) as exc:
            errors.append({"source": raw, "error": str(exc)})
    for path in entries:
        source = os.path.normcase(str(path.resolve()))
        try:
            if path.resolve().is_relative_to(svc.config.data_dir.resolve()):
                raise ValueError("Choose original screenshots outside the application's own data folder.")
            stat = path.stat()
            results.append(import_image(svc, path.read_bytes(), source=source, title=path.name,
                                        at=given_at if given_at is not None else _timestamp(stat.st_mtime),
                                        time_basis="provided" if given_at is not None else "file_mtime", app=args.app))
        except (OSError, ValueError, AppError) as exc:
            errors.append({"source": source, "error": str(exc)})
    return {"frames": results, "imported": sum(not x["duplicate"] for x in results),
            "duplicates": sum(x["duplicate"] for x in results), "errors": errors, "queue_depth": svc.ocr.depth}
