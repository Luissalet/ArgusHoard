"""Group consecutive frames of the same app + window into sessions.

A day at 5 s ticks can hold thousands of frames; a session is the unit people
think in: "the terminal, 17:02-17:41, 63 screens". The same grouping serves
`GET /api/sessions` and the activity tool.
"""

from __future__ import annotations

from .timeparse import iso_local

PREVIEW_THUMBS = 6


def group_sessions(rows, preview: int = PREVIEW_THUMBS) -> list[dict]:
    """`rows` are frames ordered by captured_at ascending with id, captured_at, until_at, app, window_title."""
    sessions: list[dict] = []
    current: dict | None = None
    for row in rows:
        key = (row["app"], row["window_title"])
        if current is not None and current["_key"] == key:
            current["end_at"] = max(current["end_at"], float(row["until_at"]))
            current["ids"].append(row["id"])
            current["seconds"] += float(row["until_at"]) - float(row["captured_at"])
            continue
        current = {
            "_key": key,
            "app": row["app"],
            "window_title": row["window_title"],
            "start_at": float(row["captured_at"]),
            "end_at": float(row["until_at"]),
            "ids": [row["id"]],
            "seconds": float(row["until_at"]) - float(row["captured_at"]),
        }
        sessions.append(current)
    out = []
    for s in sessions:
        ids = s["ids"]
        step = max(1, len(ids) // preview) if len(ids) > preview else 1
        thumbs = ids[::step][:preview]
        if ids[-1] not in thumbs and len(ids) > 1:
            thumbs = thumbs[: preview - 1] + [ids[-1]]
        out.append(
            {
                "app": s["app"],
                "window_title": s["window_title"],
                "start": iso_local(s["start_at"]),
                "end": iso_local(s["end_at"]),
                "start_at": s["start_at"],
                "end_at": s["end_at"],
                "duration_s": round(s["seconds"]),
                "count": len(ids),
                "first_id": ids[0],
                "last_id": ids[-1],
                "thumbs": thumbs,
            }
        )
    return out
