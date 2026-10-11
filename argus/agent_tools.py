"""Tools exposed to the assistant. One list drives /api/agent/*, and mcp_server.py."""

from __future__ import annotations

import time
from typing import Any

from typing import Literal

from pydantic import BaseModel, Field

from .hoard_link.agentkit import AppError, Empty, Tool, ann, call_tool as run_tool, tool_catalog as catalog_of
from .services import Services
from .timeparse import resolve_range, to_epoch
from .visual import VisualUnavailable

AGENT_INSTRUCTIONS = """Argus's Hoard is the user's own screen history: periodic screenshots of their PC, OCR'd and searchable, stored only on their machine.
Quote OCR text as OCR text: it may contain recognition errors, and a window title is what the app reported, not a fact you verified.
Never speculate beyond what the frames show; if a frame lacks text (ocr_status != done) say so instead of guessing.
screen_search also finds screens by how they looked (mode visual or both, the default): describe the scene ("la gráfica azul", "código en fondo oscuro", "a blue bar chart"). A visual hit has via ["visual"] and a visual_score (cosine, about 0.2-0.35 for a real match); it exists only once the image index is built (screen_status, visual), otherwise the search is text only. screen_similar finds screens that look like a given frame.
Prefer screen_recent (what was just on screen) and screen_search (find a word) before screen_timeline (browse a period). A screen_search hit is a moment (count frames between first_at and last_at); pass its id to screen_frame_text for the full text.
Times accept ISO datetimes and phrases in Spanish or English: "hoy", "ayer", "hace 2 horas", "esta mañana", "today", "yesterday", "2 hours ago".
If a tool reports state paused, private or disabled, tell the user plainly that Argus is not recording right now. idle_since/idle_s in screen_status mean the active screen has not changed since then (no new frames, nothing to OCR).
Only call screen_pause, screen_resume or screen_delete_range when the user explicitly asks for that action; deleting is permanent."""

TIME_HELP = "ISO datetime or a phrase such as 'hoy', 'ayer', 'hace 2 horas', 'esta mañana', 'today', '2 hours ago'."


class SearchArgs(BaseModel):
    q: str = Field(..., min_length=1, max_length=300, description="Words to find in the OCR text (all must appear; last word matches as prefix). With mode visual or both it can also describe what the screen looked like, in Spanish or English.")
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")
    app: str | None = Field(None, max_length=200, description="Restrict to one process name, e.g. 'chrome' or 'code'.")
    limit: int = Field(20, ge=1, le=100, description="How many moments to return (a moment folds consecutive near-identical frames of one window).")
    mode: Literal["text", "visual", "both"] = Field("both", description="text = OCR, titles and apps only; visual = how the screen looked (image embeddings); both = fused by rank (text only while no visual index exists).")

    model_config = {"populate_by_name": True}


class SimilarArgs(BaseModel):
    id: int = Field(..., ge=1, description="Frame id from screen_search, screen_timeline or screen_recent.")
    limit: int = Field(10, ge=1, le=50, description="How many moments.")
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")
    app: str | None = Field(None, max_length=200, description="Restrict to one process name.")

    model_config = {"populate_by_name": True}


class TimelineArgs(BaseModel):
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")
    app: str | None = Field(None, max_length=200, description="Restrict to one process name.")
    limit: int = Field(20, ge=1, le=200, description="How many entries (segments when grouped, frames otherwise).")
    group: bool = Field(True, description="Merge consecutive frames of the same app and window into one segment (compact). false = every frame.")
    cursor: float | None = Field(None, description="next_cursor from a previous call, to continue further back in time.")

    model_config = {"populate_by_name": True}


class FrameArgs(BaseModel):
    id: int = Field(..., ge=1, description="Frame id from screen_search, screen_timeline or screen_recent.")
    blocks: bool = Field(False, description="Include OCR blocks with bounding boxes.")


class PinArgs(BaseModel):
    id: int = Field(..., ge=1, description="Frame id from screen_search, screen_timeline or screen_recent.")
    pinned: bool = Field(..., description="True to keep the capture during automatic retention; false to restore normal cleanup.")


class RecentArgs(BaseModel):
    minutes: int = Field(10, ge=1, le=1440, description="Look back this many minutes.")
    limit: int = Field(8, ge=1, le=50, description="Maximum distinct frames to return.")


class RangeArgs(BaseModel):
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")

    model_config = {"populate_by_name": True}


class DeleteRangeArgs(BaseModel):
    from_: str = Field(..., alias="from", description=f"Start bound (required). {TIME_HELP}")
    to: str = Field(..., description=f"End bound (required). {TIME_HELP}")

    model_config = {"populate_by_name": True}


def _range(args) -> tuple[float | None, float | None, dict]:
    lo, hi = resolve_range(getattr(args, "from_", None), getattr(args, "to", None))
    resolved = {"from": lo.isoformat(timespec="seconds") if lo else None, "to": hi.isoformat(timespec="seconds") if hi else None}
    return to_epoch(lo), to_epoch(hi), resolved


def _state_note(services: Services) -> dict:
    state = services.recorder.state()
    return {"state": state, "recording": state == "watching"}


def _human(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


def run_status(services: Services, _: Empty) -> dict:
    s = services.status()
    keep = ("state", "enabled", "paused", "private", "interval_s", "capture_scope", "monitors", "active_monitor", "idle_since",
            "idle_s", "queue_depth", "ocr_backend", "last_capture_at", "last_error", "frames_total", "today", "disk_usage_bytes",
            "storage_cap_mb", "retention_days", "capture_backend")
    visual = s["visual"]
    return {**{k: s[k] for k in keep},
            "visual": {k: visual[k] for k in ("enabled", "active", "available", "indexed", "total", "pending", "model")}}


def run_search(services: Services, args: SearchArgs) -> dict:
    lo, hi, resolved = _range(args)
    try:
        result = services.search(args.q, lo, hi, args.app, args.limit, args.mode)
    except VisualUnavailable as error:
        raise AppError("visual_unavailable", str(error), status=409) from error
    hits = [
        {"id": h["id"], "time": h["captured_at"], "first_at": h["first_at"], "last_at": h["last_at"], "count": h["count"],
         "frame_ids": h["frame_ids"][:20], "duration_s": h["duration_s"], "app": h["app"], "window_title": h["window_title"], "snippet": h["snippet"],
         "via": h.get("via", ["text"]), "visual_score": h.get("visual_score")}
        for h in result["hits"]
    ]
    visual = result.get("visual") or {}
    return {**_state_note(services), "query": args.q, "mode": result.get("mode", "text"), "resolved": resolved, "hits": hits, "count": len(hits),
            "frames_matched": result.get("frames_total", 0), "moments_total": result.get("moments_total", len(hits)),
            "visual": {"used": bool(visual.get("used")), "note": visual.get("reason")}}


def run_similar(services: Services, args: SimilarArgs) -> dict:
    lo, hi, resolved = _range(args)
    try:
        result = services.visual.similar(args.id, args.limit, lo, hi, args.app)
    except VisualUnavailable as error:
        raise AppError("visual_unavailable", str(error), status=409) from error
    hits = [
        {"id": h["id"], "time": h["captured_at"], "first_at": h["first_at"], "last_at": h["last_at"], "count": h["count"],
         "frame_ids": h["frame_ids"][:20], "duration_s": h["duration_s"], "app": h["app"], "window_title": h["window_title"],
         "snippet": h["snippet"], "visual_score": h["visual_score"]}
        for h in result["hits"]
    ]
    return {**_state_note(services), "frame_id": args.id, "resolved": resolved, "hits": hits, "count": len(hits),
            "moments_total": result["moments_total"]}


def _segments(frames: list[dict], limit: int) -> tuple[list[dict], float | None]:
    """Consecutive frames (newest first) of one app + window become one segment.

    Returns up to `limit` segments and the cursor (epoch of the oldest frame used)
    when more frames remain beyond them.
    """
    segments: list[dict] = []
    for f in frames:
        last = segments[-1] if segments else None
        if last is not None and last["app"] == f["app"] and last["window_title"] == f["window_title"]:
            last["from"] = f["captured_at"]
            last["duration_s"] = round(last["duration_s"] + (f["duration_s"] or 0), 1)
            last["frames"] += 1
            if len(last["frame_ids"]) < 5:
                last["frame_ids"].append(f["id"])
            if len(f["excerpt"] or "") > len(last["excerpt"] or ""):
                last["excerpt"] = f["excerpt"]
            last["_ts"] = f["_ts"]
            continue
        if len(segments) == limit:
            return segments, segments[-1]["_ts"]
        segments.append({"id": f["id"], "from": f["captured_at"], "until": f["until_at"], "duration_s": f["duration_s"],
                         "app": f["app"], "window_title": f["window_title"], "frames": 1, "frame_ids": [f["id"]],
                         "excerpt": f["excerpt"], "_ts": f["_ts"]})
    return segments, None


def run_timeline(services: Services, args: TimelineArgs) -> dict:
    lo, hi, resolved = _range(args)
    if not args.group:
        result = services.queries.timeline(lo, hi, args.app, None, args.limit, args.cursor)
        frames = [
            {"id": f["id"], "time": f["captured_at"], "until": f["until_at"], "duration_s": f["duration_s"], "app": f["app"],
             "window_title": f["window_title"], "monitor": f["monitor"], "ocr_status": f["ocr_status"], "excerpt": f["excerpt"]}
            for f in result["frames"]
        ]
        return {**_state_note(services), "resolved": resolved, "frames": frames, "count": len(frames),
                "more": result["next_cursor"] is not None, "next_cursor": result["next_cursor"]}
    # Grouped: read enough frames to fill `limit` segments (a window kept open for an hour is
    # hundreds of frames), then fold them. The payload stays small whatever the period.
    batch = min(2000, max(200, args.limit * 25))
    result = services.queries.timeline(lo, hi, args.app, None, batch, args.cursor)
    segments, cut = _segments(result["frames"], args.limit)
    if cut is None and result["next_cursor"] is not None:
        # The batch ended inside the last segment: continue from its oldest frame next time.
        cut = segments[-1]["_ts"] if segments else result["next_cursor"]
    for seg in segments:
        seg.pop("_ts", None)
    return {**_state_note(services), "resolved": resolved, "segments": segments, "count": len(segments),
            "frames_seen": sum(s["frames"] for s in segments), "more": cut is not None, "next_cursor": cut,
            "hint": "Each segment is one app + window kept on screen; pass an id to screen_frame_text for its full text."}


def run_frame_text(services: Services, args: FrameArgs) -> dict:
    frame = services.queries.frame(args.id, with_blocks=args.blocks)
    if frame is None:
        raise LookupError(f"Frame {args.id} does not exist (it may have been deleted by retention).")
    return frame


def run_pin_frame(services: Services, args: PinArgs) -> dict:
    if not services.frames.set_pinned(args.id, args.pinned):
        return {"ok": False, "error": "Frame not found.", "id": args.id}
    return {"ok": True, "id": args.id, "pinned": args.pinned}


def run_recent(services: Services, args: RecentArgs) -> dict:
    since = time.time() - args.minutes * 60
    frames = services.queries.recent(since, args.limit)
    out = [{"id": f["id"], "time": f["captured_at"], "duration_s": f["duration_s"], "app": f["app"], "window_title": f["window_title"], "text": f["text"]} for f in frames]
    return {**_state_note(services), "minutes": args.minutes, "frames": out, "count": len(out)}


def run_activity(services: Services, args: RangeArgs) -> dict:
    lo, hi, resolved = _range(args)
    data = services.queries.apps(lo, hi)
    apps = data["apps"]
    sessions = services.queries.sessions(None, lo, hi, None)
    longest = sorted(sessions, key=lambda s: s["duration_s"], reverse=True)[:8]
    longest = [{k: s[k] for k in ("app", "window_title", "start", "end", "duration_s", "count", "first_id")} for s in longest]
    if not apps:
        summary = "No screen activity recorded in that period."
    else:
        top = ", ".join(f"{a['app'] or 'unknown'} {_human(a['seconds'])}" for a in apps[:3])
        summary = f"{_human(data['total_seconds'])} on screen across {len(apps)} apps and {len(sessions)} sessions; most time: {top}."
    return {**_state_note(services), "resolved": resolved, "total_seconds": data["total_seconds"], "apps": apps, "sessions_count": len(sessions), "longest_sessions": longest, "summary": summary}


def run_days(services: Services, _: Empty) -> dict:
    return {"days": services.queries.days()}


def run_pause(services: Services, _: Empty) -> dict:
    services.update_settings({"paused": True})
    return {"ok": True, **_state_note(services)}


def run_resume(services: Services, _: Empty) -> dict:
    services.update_settings({"paused": False, "private": False})
    return {"ok": True, **_state_note(services)}


def run_delete_range(services: Services, args: DeleteRangeArgs) -> dict:
    lo, hi, resolved = _range(args)
    deleted = services.janitor.delete_range(lo, hi)
    return {"ok": True, "deleted": deleted, "resolved": resolved}


TOOLS: list[Tool] = [
    Tool("screen_status", "Is Argus recording? State, OCR queue, last capture, disk and retention. Keywords: estado, grabando, pausado.\nWhether Argus is recording (watching, paused, private or disabled), OCR queue depth, last capture, disk usage and retention.\nSinónimos: estado, pantalla, está grabando, pausa, modo privado, espacio en disco.", Empty, ann(True), run_status),
    Tool("screen_search", "Search the screen history by text or by how it looked. Keywords: buscar en pantalla, qué vi, gráfica azul.\nText side: OCR, window titles and app names, BM25 (title weighs most). Visual side (`mode` visual or both, default both): a description like 'la gráfica azul' or 'código en fondo oscuro' finds the screen; hits carry `via` and `visual_score`. Each hit is a moment: near-identical frames of one window folded (first_at, last_at, count, frame_ids best first; `id` is that frame). Best first step for 'that error I saw'.\nSinónimos: buscar, pantalla, error que vi, texto que vi, dónde leí, ventana, aplicación, ayer, hace un rato.", SearchArgs, ann(True), run_search),
    Tool("screen_similar", "Screens that look like a given frame (visual similarity). Keywords: parecido, similar, captura.\nMoments whose screen looks like the frame `id` (image embeddings, CPU), best first, without the moment the frame belongs to. Needs the visual index; use it for 'cuándo vi algo parecido a esto'.\nSinónimos: parecido a esta pantalla, captura similar, otra vez así, ventana igual, gráfica parecida, buscar por imagen.", SimilarArgs, ann(True), run_similar),
    Tool("screen_timeline", "What was on screen during a period, newest first. Keywords: cronología, qué había en pantalla, secuencia.\nBrowse what was on screen during a period, newest first: consecutive frames of one app + window are folded into segments (from, until, duration, frames, excerpt), so a whole afternoon fits in one answer; group=false lists every frame; next_cursor pages further back. Use after screen_search/screen_recent when the user wants the sequence of events.\nSinónimos: línea de tiempo, qué estaba haciendo, cronología, historial de pantalla, ayer, esta mañana, hace 2 horas, aplicación, ventana.", TimelineArgs, ann(True), run_timeline),
    Tool("screen_frame_text", "Full OCR text of one frame (optionally its blocks with bounding boxes). Use ids returned by the other tools.\nSinónimos: texto completo, recuperar texto, captura, pantalla, leer la ventana.", FrameArgs, ann(True), run_frame_text),
    Tool("screen_pin_frame", "Pin or unpin a capture by id so automatic cleanup preserves it.\nAn explicit delete-range still removes pinned captures. Use only when the user asks to keep or unpin one.\nSinónimos: fijar captura, guardar pantalla, conservar captura, desfijar.", PinArgs, ann(False, False, True), run_pin_frame),
    Tool("screen_recent", "What the user was just looking at (last N minutes of OCR). Keywords: qué estaba haciendo, hace un rato, ahora.\nWhat the user was just looking at: OCR text of the last frames in the past N minutes, deduplicated, most recent first. Use for 'what was I doing', 'what did I just read', 'hace un rato'.\nSinónimos: qué estaba haciendo, hace un rato, ahora mismo, lo último que vi, pantalla actual, ventana, recuperar texto.", RecentArgs, ann(True), run_recent),
    Tool("screen_activity", "Time spent per app and window in a period, with a summary. Keywords: actividad, cuánto tiempo, en qué apps.\nTime spent per app in a period, with the top window titles per app, the longest sessions (consecutive frames of one app + window) and a one-line human summary. Durations come from how long each frame stayed on screen.\nSinónimos: actividad, en qué he perdido el tiempo, cuánto tiempo, aplicación, ventana, hoy, ayer, esta semana, resumen del día.", RangeArgs, ann(True), run_activity),
    Tool("screen_days", "Days that have screen data, with frames, hidden ticks (excluded apps) and seconds on screen per day.\nSinónimos: días, qué días hay, historial, calendario, pantalla.", Empty, ann(True), run_days),
    Tool("screen_pause", "Pause screen recording until resumed (only when asked). Keywords: pausar, deja de grabar, privado.\nPause recording until screen_resume is called (or the user resumes from the app). Only when the user asks for it.\nSinónimos: pausa, parar, deja de grabar, deja de mirar, pantalla.", Empty, ann(False, False, True), run_pause),
    Tool("screen_resume", "Resume recording (also leaves private mode). Only when the user asks for it.\nSinónimos: reanudar, continuar, vuelve a grabar, vuelve a mirar, pantalla.", Empty, ann(False, False, True), run_resume),
    Tool("screen_delete_range", "Permanently delete frames between two times (only when asked; no undo). Keywords: borrar, eliminar capturas.\nPermanently delete every frame (images and text) between two times. Only when the user explicitly asks; there is no undo.\nSinónimos: borrar, eliminar, olvidar, borra lo de ayer, borra esta tarde, privacidad, pantalla.", DeleteRangeArgs, ann(False, True, True), run_delete_range),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tool_catalog() -> list[dict]:
    return catalog_of(TOOLS)


def call_tool(services: Services, name: str, arguments: dict | None, *, cap: bool = True) -> Any:
    """Run one tool through the shared agent kit (argument validation, result cap). An expected "not found"
    (`LookupError`) keeps the 404 it always had; a bare `ValueError` is a 400 `invalid`."""
    try:
        return run_tool(TOOLS_BY_NAME, services, name, arguments, cap=cap)
    except LookupError as error:
        if isinstance(error, KeyError):  # an unknown tool: the router answers 404 unknown_tool itself
            raise
        raise AppError("not_found", str(error), status=404) from error
