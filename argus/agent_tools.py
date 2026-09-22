"""Tools exposed to the assistant. One list drives /api/agent/*, and mcp_server.py."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from .services import Services
from .timeparse import resolve_range, to_epoch

AGENT_INSTRUCTIONS = """Argus's Hoard is the user's own screen history: periodic screenshots of their PC, OCR'd and searchable, stored only on their machine.
Quote OCR text as OCR text: it may contain recognition errors, and a window title is what the app reported, not a fact you verified.
Never speculate beyond what the frames show; if a frame lacks text (ocr_status != done) say so instead of guessing.
Prefer screen_recent (what was just on screen) and screen_search (find a word) before screen_timeline (browse a period).
Times accept ISO datetimes and phrases in Spanish or English: "hoy", "ayer", "hace 2 horas", "esta mañana", "today", "yesterday", "2 hours ago".
If a tool reports state paused, private or disabled, tell the user plainly that Argus is not recording right now. idle_since/idle_s in screen_status mean the active screen has not changed since then (no new frames, nothing to OCR).
Only call screen_pause, screen_resume or screen_delete_range when the user explicitly asks for that action; deleting is permanent."""

TIME_HELP = "ISO datetime or a phrase such as 'hoy', 'ayer', 'hace 2 horas', 'esta mañana', 'today', '2 hours ago'."


class Empty(BaseModel):
    pass


class SearchArgs(BaseModel):
    q: str = Field(..., min_length=1, max_length=300, description="Words to find in the OCR text (all must appear; last word matches as prefix).")
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")
    app: str | None = Field(None, max_length=200, description="Restrict to one process name, e.g. 'chrome' or 'code'.")
    limit: int = Field(20, ge=1, le=100)

    model_config = {"populate_by_name": True}


class TimelineArgs(BaseModel):
    from_: str | None = Field(None, alias="from", description=f"Start bound. {TIME_HELP}")
    to: str | None = Field(None, description=f"End bound. {TIME_HELP}")
    app: str | None = Field(None, max_length=200, description="Restrict to one process name.")
    limit: int = Field(40, ge=1, le=200)

    model_config = {"populate_by_name": True}


class FrameArgs(BaseModel):
    id: int = Field(..., ge=1, description="Frame id from screen_search, screen_timeline or screen_recent.")
    blocks: bool = Field(False, description="Include OCR blocks with bounding boxes.")


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


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    annotations: dict[str, bool]
    run: Callable[[Services, Any], Any]


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
    return {k: s[k] for k in keep}


def run_search(services: Services, args: SearchArgs) -> dict:
    lo, hi, resolved = _range(args)
    result = services.queries.search(args.q, lo, hi, args.app, args.limit)
    hits = [
        {"id": h["id"], "time": h["captured_at"], "duration_s": h["duration_s"], "app": h["app"], "window_title": h["window_title"], "snippet": h["snippet"]}
        for h in result["hits"]
    ]
    return {**_state_note(services), "query": args.q, "resolved": resolved, "hits": hits, "count": len(hits)}


def run_timeline(services: Services, args: TimelineArgs) -> dict:
    lo, hi, resolved = _range(args)
    result = services.queries.timeline(lo, hi, args.app, None, args.limit, None)
    frames = [
        {"id": f["id"], "time": f["captured_at"], "until": f["until_at"], "duration_s": f["duration_s"], "app": f["app"],
         "window_title": f["window_title"], "monitor": f["monitor"], "ocr_status": f["ocr_status"], "excerpt": f["excerpt"]}
        for f in result["frames"]
    ]
    return {**_state_note(services), "resolved": resolved, "frames": frames, "count": len(frames), "more": result["next_cursor"] is not None}


def run_frame_text(services: Services, args: FrameArgs) -> dict:
    frame = services.queries.frame(args.id, with_blocks=args.blocks)
    if frame is None:
        raise LookupError(f"Frame {args.id} does not exist (it may have been deleted by retention).")
    return frame


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


def _ann(read_only: bool, destructive: bool = False, idempotent: bool | None = None) -> dict[str, bool]:
    return {"readOnlyHint": read_only, "destructiveHint": destructive, "idempotentHint": read_only if idempotent is None else idempotent, "openWorldHint": False}


TOOLS: list[Tool] = [
    Tool("screen_status", "Whether Argus is recording (watching, paused, private or disabled), OCR queue depth, last capture, disk usage and retention.\nSinónimos: estado, pantalla, está grabando, pausa, modo privado, espacio en disco.", Empty, _ann(True), run_status),
    Tool("screen_search", "Full-text search over everything that was on screen (OCR text, window titles, app names) with BM25 ranking and a snippet per frame. Best first step for 'that error I saw' or 'where did I read X'.\nSinónimos: buscar, pantalla, error que vi, texto que vi, dónde leí, recuperar texto, ventana, aplicación, ayer, hace un rato.", SearchArgs, _ann(True), run_search),
    Tool("screen_timeline", "Browse what was on screen during a period, newest first, with app, window title, duration and a text excerpt per frame. Use after screen_search/screen_recent when the user wants the sequence of events.\nSinónimos: línea de tiempo, qué estaba haciendo, cronología, historial de pantalla, ayer, esta mañana, hace 2 horas, aplicación, ventana.", TimelineArgs, _ann(True), run_timeline),
    Tool("screen_frame_text", "Full OCR text of one frame (optionally its blocks with bounding boxes). Use ids returned by the other tools.\nSinónimos: texto completo, recuperar texto, captura, pantalla, leer la ventana.", FrameArgs, _ann(True), run_frame_text),
    Tool("screen_recent", "What the user was just looking at: OCR text of the last frames in the past N minutes, deduplicated, most recent first. Use for 'what was I doing', 'what did I just read', 'hace un rato'.\nSinónimos: qué estaba haciendo, hace un rato, ahora mismo, lo último que vi, pantalla actual, ventana, recuperar texto.", RecentArgs, _ann(True), run_recent),
    Tool("screen_activity", "Time spent per app in a period, with the top window titles per app, the longest sessions (consecutive frames of one app + window) and a one-line human summary. Durations come from how long each frame stayed on screen.\nSinónimos: actividad, en qué he perdido el tiempo, cuánto tiempo, aplicación, ventana, hoy, ayer, esta semana, resumen del día.", RangeArgs, _ann(True), run_activity),
    Tool("screen_days", "Days that have screen data, with frames, hidden ticks (excluded apps) and seconds on screen per day.\nSinónimos: días, qué días hay, historial, calendario, pantalla.", Empty, _ann(True), run_days),
    Tool("screen_pause", "Pause recording until screen_resume is called (or the user resumes from the app). Only when the user asks for it.\nSinónimos: pausa, parar, deja de grabar, deja de mirar, pantalla.", Empty, _ann(False, False, True), run_pause),
    Tool("screen_resume", "Resume recording (also leaves private mode). Only when the user asks for it.\nSinónimos: reanudar, continuar, vuelve a grabar, vuelve a mirar, pantalla.", Empty, _ann(False, False, True), run_resume),
    Tool("screen_delete_range", "Permanently delete every frame (images and text) between two times. Only when the user explicitly asks; there is no undo.\nSinónimos: borrar, eliminar, olvidar, borra lo de ayer, borra esta tarde, privacidad, pantalla.", DeleteRangeArgs, _ann(False, True, True), run_delete_range),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tool_catalog() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "annotations": t.annotations, "inputSchema": t.input_model.model_json_schema(by_alias=True)}
        for t in TOOLS
    ]


def call_tool(services: Services, name: str, arguments: dict | None) -> Any:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    args = tool.input_model.model_validate(arguments or {})
    return tool.run(services, args)
