"""Visual search: status, model download and re-indexing. The search itself is `GET /api/search?mode=` and `GET /api/frames/{id}/similar`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .deps import services

router = APIRouter(prefix="/api/visual")


@router.get("")
def visual_status(request: Request):
    return services(request).visual.status()


@router.post("/download")
def visual_download(request: Request):
    """Start downloading the model (about 300 MB, once) in the background; poll `GET /api/visual` for `download`."""
    return services(request).visual.start_download()


@router.post("/reindex")
def visual_reindex(request: Request):
    """Forget every vector so the indexer embeds all frames again (after changing the model, or to start clean)."""
    svc = services(request)
    return {"ok": True, "removed": svc.visual.reindex()}
