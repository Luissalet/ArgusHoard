"""Read path: timeline, frame detail, full-text search, activity by app, days."""

from __future__ import annotations

import re
import time

from .db import Database
from .search import Candidate, group_moments, idf, query_terms, rank_candidates
from .sessions import group_sessions
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

    def _range_clause(self, start: float | None, end: float | None, app: str | None, title: str | None = None):
        clauses, params = [], []
        if title is not None:
            clauses.append("f.window_title = ?")
            params.append(title)
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
        title: str | None = None,
    ) -> dict:
        clauses, params = self._range_clause(start, end, app, title)
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
        frames = [{**_frame_row(row), "excerpt": _excerpt(row["text"]), "_ts": float(row["captured_at"])} for row in rows[:limit]]
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

    def _avg_text_tokens(self) -> float:
        """Average OCR text length in tokens (chars / 6), cached for a minute."""
        cached = getattr(self, "_avg_cache", None)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        with self.db.lock:
            row = self.db.conn.execute("SELECT AVG(LENGTH(text)) AS chars FROM frames_fts").fetchone()
        value = max(1.0, float(row["chars"] or 0) / 6.0)
        self._avg_cache = (time.time(), value)
        return value

    def search(self, q: str, start: float | None, end: float | None, app: str | None, limit: int, group_window_s: int = 600) -> dict:
        """FTS5 finds candidates; `argus.search` re-ranks them and collapses runs into moments."""
        match = fts_query(q)
        terms = query_terms(q)
        if not match or not terms:
            return {"query": q, "hits": [], "frames_total": 0}
        clauses, params = self._range_clause(start, end, app)
        where = ("AND " + " AND ".join(clauses)) if clauses else ""
        candidate_limit = max(400, limit * 25)
        sql = f"""SELECT f.*, frames_fts.text AS text, bm25(frames_fts, 1.0, 3.0, 2.0) AS fts_rank,
                         snippet(frames_fts, 0, '[', ']', '…', 18) AS snip
                  FROM frames_fts JOIN frames f ON f.id = frames_fts.rowid
                  WHERE frames_fts MATCH ? {where}
                  ORDER BY fts_rank LIMIT ?"""
        with self.db.lock:
            rows = self.db.conn.execute(sql, [match, *params, candidate_limit]).fetchall()
            total = int(self.db.conn.execute("SELECT COUNT(*) AS n FROM frames_fts").fetchone()["n"])
            idfs = {}
            for term, prefix in terms:
                hits = int(self.db.conn.execute(
                    "SELECT COUNT(*) AS n FROM frames_fts WHERE frames_fts MATCH ?", (f'"{term}"*' if prefix else f'"{term}"',)
                ).fetchone()["n"])
                idfs[term] = idf(total, hits)
        candidates = [
            Candidate(row["id"], float(row["captured_at"]), row["app"], row["window_title"], row["text"] or "",
                      re.sub(r"\s+", " ", row["snip"] or "").strip(), dict(row))
            for row in rows
        ]
        ranked = rank_candidates(candidates, terms, idfs, self._avg_text_tokens())
        moments = group_moments(ranked, group_window_s)[:limit]
        hits = []
        for moment in moments:
            best = moment["best"]
            hits.append({
                **_frame_row(best.row),
                "snippet": best.snippet,
                "rank": round(moment["rank"], 4),
                "first_at": iso_local(moment["first_at"]),
                "last_at": iso_local(moment["last_at"]),
                "count": moment["count"],
                "frame_ids": moment["frame_ids"],
                "duration_s": round(sum(max(0.0, float(c.row["until_at"]) - float(c.row["captured_at"])) for c, _ in moment["members"]), 1),
            })
        return {"query": q, "match": match, "hits": hits, "frames_total": len(candidates), "moments_total": len(group_moments(ranked, group_window_s))}

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

    def sessions(self, day: str | None = None, start: float | None = None, end: float | None = None, app: str | None = None) -> list[dict]:
        """Consecutive frames of the same app + window, oldest first."""
        clauses, params = self._range_clause(start, end, app)
        if day:
            clauses.append("f.day = ?")
            params.append(day)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.lock:
            rows = self.db.conn.execute(
                f"SELECT f.id, f.captured_at, f.until_at, f.app, f.window_title FROM frames f {where} ORDER BY f.captured_at ASC, f.monitor ASC",
                params,
            ).fetchall()
        return group_sessions(rows)

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
