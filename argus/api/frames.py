"""Timeline, frame detail and images, search, activity by app, days, range deletion."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .deps import epoch_range, services

router = APIRouter(prefix="/api")


@router.get("/timeline")
def timeline(
    request: Request,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    app: str | None = Query(None, max_length=200),
    q: str | None = Query(None, max_length=300),
    limit: int = Query(60, ge=1, le=500),
    cursor: float | None = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    lo, hi = epoch_range(from_, to)
    return services(request).queries.timeline(lo, hi, app, q, limit, cursor, ascending=order == "asc")


@router.get("/frames/{frame_id}")
def frame(request: Request, frame_id: int, blocks: bool = True):
    svc = services(request)
    data = svc.queries.frame(frame_id, with_blocks=blocks)
    if data is None:
        raise HTTPException(404, "Frame not found.")
    return {**data, **svc.queries.neighbours(frame_id)}


def _file(request: Request, frame_id: int, thumb: bool):
    info = services(request).frames.image_file(frame_id)
    if info is None:
        raise HTTPException(404, "Frame not found.")
    path = info[1] if thumb else info[0]
    if not path.exists():
        raise HTTPException(404, "Image file is missing.")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/frames/{frame_id}/image")
def frame_image(request: Request, frame_id: int):
    return _file(request, frame_id, thumb=False)


@router.get("/frames/{frame_id}/thumb")
def frame_thumb(request: Request, frame_id: int):
    return _file(request, frame_id, thumb=True)


@router.get("/search")
def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=300),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    app: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
):
    lo, hi = epoch_range(from_, to)
    return services(request).queries.search(q, lo, hi, app, limit)


@router.get("/apps")
def apps(request: Request, from_: str | None = Query(None, alias="from"), to: str | None = None):
    lo, hi = epoch_range(from_, to)
    return services(request).queries.apps(lo, hi)


@router.get("/days")
def days(request: Request):
    return {"days": services(request).queries.days()}


@router.delete("/frames")
def delete_frames(request: Request, from_: str = Query(..., alias="from"), to: str = Query(...)):
    lo, hi = epoch_range(from_, to)
    deleted = services(request).janitor.delete_range(lo, hi)
    return {"ok": True, "deleted": deleted}


@router.post("/janitor")
def run_janitor(request: Request):
    return services(request).janitor.run()
