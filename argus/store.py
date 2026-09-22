"""Write path of the frame store: insert/extend frames, OCR results, deletion, stats."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import images
from .db import Database
from .exclusions import Rule, validate_pattern
from .timeparse import day_of


@dataclass
class Block:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float = 0.0


@dataclass
class LastFrame:
    id: int
    phash: str
    until_at: float
    window_title: str
    app: str


class FrameStore:
    def __init__(self, db: Database, frames_dir: Path):
        self.db = db
        self.frames_dir = frames_dir

    # ---------- capture path ----------
    def last_frame(self, monitor: int) -> LastFrame | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT id, phash, until_at, window_title, app FROM frames WHERE monitor = ? ORDER BY captured_at DESC LIMIT 1",
                (monitor,),
            ).fetchone()
        return LastFrame(row["id"], row["phash"], row["until_at"], row["window_title"], row["app"]) if row else None

    def extend_frame(self, frame_id: int, until_at: float) -> None:
        with self.db.lock:
            self.db.conn.execute("UPDATE frames SET until_at = MAX(until_at, ?) WHERE id = ?", (until_at, frame_id))

    def insert_frame(
        self,
        image: Image.Image,
        *,
        captured_at: float,
        interval_s: int,
        monitor: int,
        app: str,
        window_title: str,
        phash: str,
        image_max_width: int = 1280,
        thumb_max_width: int = 320,
    ) -> int:
        day = day_of(captured_at)
        with self.db.lock:
            cursor = self.db.conn.execute(
                """INSERT INTO frames(captured_at, until_at, day, monitor, app, window_title, image_path, thumb_path,
                                      width, height, phash, ocr_status)
                   VALUES (?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, 'pending')""",
                (captured_at, captured_at + interval_s, day, monitor, app, window_title, image.width, image.height, phash),
            )
            frame_id = int(cursor.lastrowid)
        image_path, thumb_path = images.frame_paths(self.frames_dir, day, frame_id)
        try:
            size = images.save_frame_images(image, image_path, thumb_path, image_max_width, thumb_max_width)
        except Exception:
            with self.db.lock:  # never leave a frame row without its image
                self.db.conn.execute("DELETE FROM frames WHERE id = ?", (frame_id,))
            images.remove_images(image_path, thumb_path)
            raise
        rel_image = image_path.relative_to(self.frames_dir).as_posix()
        rel_thumb = thumb_path.relative_to(self.frames_dir).as_posix()
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE frames SET image_path = ?, thumb_path = ?, bytes = ? WHERE id = ?",
                (rel_image, rel_thumb, size, frame_id),
            )
            self.db.conn.execute(
                "INSERT INTO daily_stats(day, frames) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET frames = frames + 1",
                (day,),
            )
        return frame_id

    def record_tick(self, captured_at: float, hidden: bool) -> None:
        day = day_of(captured_at)
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO daily_stats(day, hidden, ticks) VALUES (?, ?, 1) "
                "ON CONFLICT(day) DO UPDATE SET hidden = hidden + excluded.hidden, ticks = ticks + 1",
                (day, 1 if hidden else 0),
            )

    # ---------- OCR path ----------
    def pending_frames(self, limit: int = 20) -> list[int]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT id FROM frames WHERE ocr_status = 'pending' ORDER BY captured_at ASC LIMIT ?", (limit,)
            ).fetchall()
        return [row["id"] for row in rows]

    def image_file(self, frame_id: int) -> tuple[Path, Path, int, int] | None:
        """(image path, thumbnail path, original width, original height)."""
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT image_path, thumb_path, width, height FROM frames WHERE id = ?", (frame_id,)
            ).fetchone()
        if not row or not row["image_path"]:
            return None
        return self.frames_dir / row["image_path"], self.frames_dir / row["thumb_path"], row["width"], row["height"]

    def set_ocr_result(self, frame_id: int, blocks: list[Block], text: str, ms: int, backend: str) -> None:
        with self.db.lock:
            row = self.db.conn.execute("SELECT window_title, app FROM frames WHERE id = ?", (frame_id,)).fetchone()
            if row is None:
                return
            self.db.conn.execute("BEGIN")
            try:
                self.db.conn.execute("DELETE FROM blocks WHERE frame_id = ?", (frame_id,))
                self.db.conn.executemany(
                    "INSERT INTO blocks(frame_id, text, x, y, w, h, conf) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(frame_id, b.text, b.x, b.y, b.w, b.h, b.conf) for b in blocks],
                )
                self.db.conn.execute("DELETE FROM frames_fts WHERE rowid = ?", (frame_id,))
                self.db.conn.execute(
                    "INSERT INTO frames_fts(rowid, text, window_title, app) VALUES (?, ?, ?, ?)",
                    (frame_id, text, row["window_title"], row["app"]),
                )
                self.db.conn.execute(
                    "UPDATE frames SET ocr_status = 'done', ocr_ms = ?, ocr_backend = ? WHERE id = ?",
                    (ms, backend, frame_id),
                )
                self.db.conn.execute("COMMIT")
            except Exception:
                self.db.conn.execute("ROLLBACK")
                raise

    def set_ocr_status(self, frame_id: int, status: str, backend: str | None = None) -> None:
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE frames SET ocr_status = ?, ocr_backend = COALESCE(?, ocr_backend) WHERE id = ?",
                (status, backend, frame_id),
            )

    # ---------- deletion / retention ----------
    def delete_frames(self, ids: list[int]) -> int:
        if not ids:
            return 0
        deleted = 0
        for start in range(0, len(ids), 200):
            chunk = ids[start : start + 200]
            marks = ",".join("?" * len(chunk))
            with self.db.lock:
                rows = self.db.conn.execute(
                    f"SELECT id, image_path, thumb_path FROM frames WHERE id IN ({marks})", chunk
                ).fetchall()
                self.db.conn.execute("BEGIN")
                try:
                    self.db.conn.execute(f"DELETE FROM blocks WHERE frame_id IN ({marks})", chunk)
                    self.db.conn.execute(f"DELETE FROM frames_fts WHERE rowid IN ({marks})", chunk)
                    self.db.conn.execute(f"DELETE FROM frames WHERE id IN ({marks})", chunk)
                    self.db.conn.execute("COMMIT")
                except Exception:
                    self.db.conn.execute("ROLLBACK")
                    raise
            for row in rows:
                if row["image_path"]:
                    images.remove_images(self.frames_dir / row["image_path"], self.frames_dir / row["thumb_path"])
                deleted += 1
        return deleted

    def frame_ids_between(self, start: float | None, end: float | None) -> list[int]:
        clauses, params = [], []
        if start is not None:
            clauses.append("until_at > ?")
            params.append(start)
        if end is not None:
            clauses.append("captured_at < ?")
            params.append(end)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.lock:
            rows = self.db.conn.execute(f"SELECT id FROM frames {where} ORDER BY captured_at", params).fetchall()
        return [row["id"] for row in rows]

    def frame_ids_older_than(self, cutoff: float) -> list[int]:
        with self.db.lock:
            rows = self.db.conn.execute("SELECT id FROM frames WHERE captured_at < ? ORDER BY captured_at", (cutoff,)).fetchall()
        return [row["id"] for row in rows]

    def oldest_frames_over_cap(self, cap_bytes: int) -> list[int]:
        """Ids of the oldest frames whose removal brings disk usage under the cap."""
        total = self.disk_usage()
        if total <= cap_bytes:
            return []
        excess = total - cap_bytes
        with self.db.lock:
            rows = self.db.conn.execute("SELECT id, bytes FROM frames ORDER BY captured_at ASC").fetchall()
        ids, freed = [], 0
        for row in rows:
            if freed >= excess:
                break
            ids.append(row["id"])
            freed += row["bytes"]
        return ids

    def disk_usage(self) -> int:
        with self.db.lock:
            row = self.db.conn.execute("SELECT COALESCE(SUM(bytes), 0) AS total FROM frames").fetchone()
        return int(row["total"])

    def frame_count(self) -> int:
        with self.db.lock:
            return int(self.db.conn.execute("SELECT COUNT(*) AS n FROM frames").fetchone()["n"])

    def today_stats(self, now: float | None = None) -> dict:
        day = day_of(now or time.time())
        with self.db.lock:
            row = self.db.conn.execute("SELECT frames, hidden, ticks FROM daily_stats WHERE day = ?", (day,)).fetchone()
        return {"day": day, "frames": row["frames"] if row else 0, "hidden": row["hidden"] if row else 0, "ticks": row["ticks"] if row else 0}


class ExclusionStore:
    def __init__(self, db: Database):
        self.db = db
        self._cache: list[Rule] | None = None

    def list(self) -> list[Rule]:
        if self._cache is None:
            with self.db.lock:
                rows = self.db.conn.execute("SELECT id, kind, pattern, enabled FROM exclusions ORDER BY id").fetchall()
            self._cache = [Rule(row["id"], row["kind"], row["pattern"], bool(row["enabled"])) for row in rows]
        return self._cache

    def add(self, kind: str, pattern: str) -> Rule:
        error = validate_pattern(kind, pattern)
        if error:
            raise ValueError(error)
        pattern = pattern.strip()
        with self.db.lock:
            existing = self.db.conn.execute(
                "SELECT id, kind, pattern, enabled FROM exclusions WHERE kind = ? AND pattern = ?", (kind, pattern)
            ).fetchone()
            if existing:
                return Rule(existing["id"], existing["kind"], existing["pattern"], bool(existing["enabled"]))
            cursor = self.db.conn.execute(
                "INSERT INTO exclusions(kind, pattern, enabled, created_at) VALUES (?, ?, 1, ?)", (kind, pattern, time.time())
            )
        self._cache = None
        return Rule(int(cursor.lastrowid), kind, pattern, True)

    def set_enabled(self, rule_id: int, enabled: bool) -> bool:
        with self.db.lock:
            changed = self.db.conn.execute("UPDATE exclusions SET enabled = ? WHERE id = ?", (1 if enabled else 0, rule_id)).rowcount
        self._cache = None
        return changed > 0

    def remove(self, rule_id: int) -> bool:
        with self.db.lock:
            changed = self.db.conn.execute("DELETE FROM exclusions WHERE id = ?", (rule_id,)).rowcount
        self._cache = None
        return changed > 0
