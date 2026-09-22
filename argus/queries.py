"""Read path: timeline, frame detail, full-text search, activity by app, days."""

from __future__ import annotations

import re

from .db import Database
from .timeparse import iso_local

EXCERPT_CHARS = 240


def _excerpt(text: str | None, limit: int = EXCERPT_CHARS) -> str:
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def fts_query(raw: str) -> str:
    """Build a safe FTS5 MATCH expression: quoted tokens, implicit AND, prefix on the last."""
    tokens = [t for t in re.findall(r"[\w'’\-]+", raw, flags=re.UNICODE) if t.strip("-'’")]
    if not tokens:
        return ""
    parts = [f'"{t.replace(chr(34), "")}"' for t in tokens]
    if len(tokens[-1]) >= 3:
        parts[-1] += "*"
    return " ".join(parts)


def _frame_row(row, tz=None) -> dict:
    duration = max(0.0, float(row["until_at"]) - float(row["captured_at"]))
    return {
        "id": row["id"],
        "captured_at": iso_local(row["captured_at"], tz),
        "until_at": iso_local(row["until_at"], tz),
        "duration_s": round(duration, 1),
        "day": row["day"],
        "monitor": row["monitor"],
        "app": row["app"],
        "window_title": row["window_title"],
        "width": row["width"],
        "height": row["height"],
        "ocr_status": row["ocr_status"],
        "ocr_ms": row["ocr_ms"],
    }


class Queries:
    def __init__(self, db: Database):
        self.db = db

    def _range_clause(self, start: float | None, end: float | None, app: str | None):
        clauses, params = [], []
        if start is not None:
            clauses.append("f.until_at > ?")
            params.append(start)
        if end is not None:
            clauses.append("f.captured_at < ?")
            params.append(end)
        if app:
            clauses.append("LOWER(f.app) = LOWER(?)")
            params.append(app[:-4] if app.lower().endswith(".exe") else app)
        return clauses, params

    def timeline(
        self,
        start: float | None,
        end: float | None,
        app: str | None,
        q: str | None,
        limit: int,
        cursor: float | None,
        ascending: bool = False,
    ) -> dict:
        clauses, params = self._range_clause(start, end, app)
        if cursor is not None:
            clauses.append("f.captured_at < ?" if not ascending else "f.captured_at > ?")
            params.append(cursor)
        match = fts_query(q or "")
        join = ""
        if match:
            join = "JOIN frames_fts x ON x.rowid = f.id AND frames_fts MATCH ?"
            params.insert(0, match)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ASC" if ascending else "DESC"
        sql = f"""SELECT f.*, (SELECT text FROM frames_fts t WHERE t.rowid = f.id) AS text
                  FROM frames f {join} {where} ORDER BY f.captured_at {order} LIMIT ?"""
        with self.db.lock:
            rows = self.db.conn.execute(sql, [*params, limit + 1]).fetchall()
        frames = [{**_frame_row(row), "excerpt": _excerpt(row["text"])} for row in rows[:limit]]
        next_cursor = rows[limit - 1]["captured_at"] if len(rows) > limit else None
        return {"frames": frames, "next_cursor": next_cursor}

    def frame(self, frame_id: int, with_blocks: bool = True) -> dict | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT f.*, (SELECT text FROM frames_fts t WHERE t.rowid = f.id) AS text FROM frames f WHERE f.id = ?",
                (frame_id,),
            ).fetchone()
            if row is None:
                return None
            blocks = []
            if with_blocks:
                blocks = [
                    dict(b)
                    for b in self.db.conn.execute(
                        "SELECT text, x, y, w, h, conf FROM blocks WHERE frame_id = ? ORDER BY y, x", (frame_id,)
                    ).fetchall()
                ]
        result = {**_frame_row(row), "text": row["text"] or "", "ocr_backend": row["ocr_backend"]}
        if with_blocks:
            result["blocks"] = blocks
        return result

    def neighbours(self, frame_id: int) -> dict:
        with self.db.lock:
            row = self.db.conn.execute("SELECT captured_at FROM frames WHERE id = ?", (frame_id,)).fetchone()
            if row is None:
                return {"prev": None, "next": None}
            prev = self.db.conn.execute(
                "SELECT id FROM frames WHERE captured_at < ? ORDER BY captured_at DESC LIMIT 1", (row["captured_at"],)
            ).fetchone()
            nxt = self.db.conn.execute(
                "SELECT id FROM frames WHERE captured_at > ? ORDER BY captured_at ASC LIMIT 1", (row["captured_at"],)
            ).fetchone()
        return {"prev": prev["id"] if prev else None, "next": nxt["id"] if nxt else None}

    def search(self, q: str, start: float | None, end: float | None, app: str | None, limit: int) -> dict:
        match = fts_query(q)
        if not match:
            return {"query": q, "hits": []}
        clauses, params = self._range_clause(start, end, app)
        where = ("AND " + " AND ".join(clauses)) if clauses else ""
        sql = f"""SELECT f.*, bm25(frames_fts, 1.0, 3.0, 2.0) AS rank,
                         snippet(frames_fts, 0, '[', ']', '…', 18) AS snip
                  FROM frames_fts JOIN frames f ON f.id = frames_fts.rowid
                  WHERE frames_fts MATCH ? {where}
                  ORDER BY rank LIMIT ?"""
        with self.db.lock:
            rows = self.db.conn.execute(sql, [match, *params, limit]).fetchall()
        hits = [{**_frame_row(row), "snippet": re.sub(r"\s+", " ", row["snip"] or "").strip(), "rank": round(row["rank"], 3)} for row in rows]
        return {"query": q, "match": match, "hits": hits}

    def apps(self, start: float | None, end: float | None, titles_per_app: int = 5) -> dict:
        clauses, params = self._range_clause(start, end, None)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.lock:
            totals = self.db.conn.execute(
                f"""SELECT f.app, SUM(f.until_at - f.captured_at) AS seconds, COUNT(*) AS frames
                    FROM frames f {where} GROUP BY f.app ORDER BY seconds DESC""",
                params,
            ).fetchall()
            titles = self.db.conn.execute(
                f"""SELECT app, window_title, seconds FROM (
                      SELECT f.app, f.window_title, SUM(f.until_at - f.captured_at) AS seconds,
                             ROW_NUMBER() OVER (PARTITION BY f.app ORDER BY SUM(f.until_at - f.captured_at) DESC) AS rn
                      FROM frames f {where} GROUP BY f.app, f.window_title)
                    WHERE rn <= ? ORDER BY app, seconds DESC""",
                [*params, titles_per_app],
            ).fetchall()
        by_app: dict[str, list] = {}
        for row in titles:
            by_app.setdefault(row["app"], []).append({"window_title": row["window_title"], "seconds": round(row["seconds"])})
        apps = [
            {"app": row["app"], "seconds": round(row["seconds"]), "frames": row["frames"], "top_windows": by_app.get(row["app"], [])}
            for row in totals
        ]
        return {"apps": apps, "total_seconds": round(sum(a["seconds"] for a in apps))}

    def days(self) -> list[dict]:
        with self.db.lock:
            rows = self.db.conn.execute(
                """SELECT s.day, s.frames AS captured, s.hidden, s.ticks,
                          (SELECT COUNT(*) FROM frames f WHERE f.day = s.day) AS frames,
                          (SELECT COALESCE(SUM(f.until_at - f.captured_at), 0) FROM frames f WHERE f.day = s.day) AS seconds
                   FROM daily_stats s ORDER BY s.day DESC"""
            ).fetchall()
        return [
            {"day": r["day"], "frames": r["frames"], "captured": r["captured"], "hidden": r["hidden"], "seconds": round(r["seconds"])}
            for r in rows
            if r["frames"] or r["hidden"]
        ]

    def recent(self, since: float, limit: int) -> list[dict]:
        """Most recent OCR'd frames, most recent first, one per distinct text."""
        with self.db.lock:
            rows = self.db.conn.execute(
                """SELECT f.*, t.text FROM frames f JOIN frames_fts t ON t.rowid = f.id
                   WHERE f.until_at >= ? AND f.ocr_status = 'done' ORDER BY f.captured_at DESC LIMIT ?""",
                (since, limit * 4),
            ).fetchall()
        seen: set[str] = set()
        out = []
        for row in rows:
            key = re.sub(r"\s+", " ", (row["text"] or "")).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({**_frame_row(row), "text": row["text"]})
            if len(out) >= limit:
                break
        return out
