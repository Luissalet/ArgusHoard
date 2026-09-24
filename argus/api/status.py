"""Health, status, settings, recording controls and exclusion rules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import __version__
from ..exclusions import first_match
from ..settings import SettingsPatch
from .deps import services
from ..hoard_link import family

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    return {"service": "argus-hoard", "version": __version__, "dataDirConfigured": request.app.state.config.data_dir_configured,
            "hoard_link": family.health_block()}


@router.get("/status")
def status(request: Request):
    return services(request).status()


@router.get("/settings")
def get_settings(request: Request):
    return services(request).settings.get()


@router.put("/settings")
def put_settings(request: Request, patch: SettingsPatch):
    return services(request).update_settings(patch)


@router.post("/pause")
def pause(request: Request):
    svc = services(request)
    svc.update_settings({"paused": True})
    return {"ok": True, "state": svc.recorder.state()}


@router.post("/resume")
def resume(request: Request):
    svc = services(request)
    svc.update_settings({"paused": False, "private": False})
    return {"ok": True, "state": svc.recorder.state()}


class PrivateBody(BaseModel):
    private: bool | None = None  # omitted = toggle


@router.post("/private")
def private(request: Request, body: PrivateBody | None = None):
    svc = services(request)
    current = svc.settings.get().private
    value = (not current) if body is None or body.private is None else body.private
    svc.update_settings({"private": value})
    return {"ok": True, "private": value, "state": svc.recorder.state()}


# ---------- exclusions ----------
class ExclusionIn(BaseModel):
    kind: str = Field(..., pattern="^(app|title)$")
    pattern: str = Field(..., min_length=1, max_length=300)


class ExclusionPatch(BaseModel):
    enabled: bool


class ExclusionTest(BaseModel):
    app: str = Field("", max_length=200)
    title: str = Field("", max_length=1000)


def _rule_json(rule):
    return {"id": rule.id, "kind": rule.kind, "pattern": rule.pattern, "enabled": rule.enabled}


@router.get("/exclusions")
def list_exclusions(request: Request):
    return {"exclusions": [_rule_json(r) for r in services(request).exclusions.list()]}


@router.post("/exclusions", status_code=201)
def add_exclusion(request: Request, body: ExclusionIn):
    try:
        rule = services(request).exclusions.add(body.kind, body.pattern)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return _rule_json(rule)


@router.patch("/exclusions/{rule_id}")
def patch_exclusion(request: Request, rule_id: int, body: ExclusionPatch):
    if not services(request).exclusions.set_enabled(rule_id, body.enabled):
        raise HTTPException(404, "Exclusion not found.")
    return {"ok": True}


@router.delete("/exclusions/{rule_id}")
def delete_exclusion(request: Request, rule_id: int):
    if not services(request).exclusions.remove(rule_id):
        raise HTTPException(404, "Exclusion not found.")
    return {"ok": True}


@router.post("/exclusions/test")
def test_exclusion(request: Request, body: ExclusionTest):
    rule = first_match(services(request).exclusions.list(), body.app, body.title)
    return {"excluded": rule is not None, "rule": _rule_json(rule) if rule else None}
