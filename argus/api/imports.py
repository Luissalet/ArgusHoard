"""Existing screenshot files and browser uploads enter the same OCR library."""
import json
from pathlib import Path
import time

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from ..imports import ScreenImportArgs, _timestamp, import_image, import_paths
from ..hoard_link.agentkit import AppError
from .deps import services

router = APIRouter(prefix="/api/imports", tags=["screenshot import"])


@router.get("")
def list_imports(request: Request, limit: int = Query(60, ge=1, le=500), before: int | None = Query(None, ge=1)):
    return services(request).queries.imported(limit, before)


@router.post("")
def paths(request: Request, body: ScreenImportArgs):
    return import_paths(services(request), body)


@router.post("/upload")
def upload(request: Request, files: list[UploadFile] = File(...), modified: str = Form("[]")):
    svc = services(request)
    try:
        dates = json.loads(modified)
    except ValueError:
        raise AppError("invalid_import_date", "Upload modification dates must be a JSON list.") from None
    if not isinstance(dates, list):
        raise AppError("invalid_import_date", "Upload modification dates must be a JSON list.")
    results, errors = [], []
    for index, file in enumerate(files):
        name = Path((file.filename or "screenshot.png").replace("\\", "/")).name
        try:
            at = _timestamp(dates[index]) if index < len(dates) else time.time()
            results.append(import_image(svc, file.file.read(), source="upload:"+name, title=name, at=at,
                                        time_basis="file_mtime" if index < len(dates) else "imported_at", app="Archivo importado"))
        except (ValueError, OSError, AppError) as exc:
            errors.append({"source": name, "error": str(exc)})
        finally:
            file.file.close()
    return {"frames": results, "imported": sum(not x["duplicate"] for x in results),
            "duplicates": sum(x["duplicate"] for x in results), "errors": errors, "queue_depth": svc.ocr.depth}
