"""Shared helpers for the API routers."""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..services import Services
from ..timeparse import resolve_range, to_epoch


def services(request: Request) -> Services:
    return request.app.state.services


def epoch_range(start: str | None, end: str | None) -> tuple[float | None, float | None]:
    try:
        lo, hi = resolve_range(start, end)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return to_epoch(lo), to_epoch(hi)
