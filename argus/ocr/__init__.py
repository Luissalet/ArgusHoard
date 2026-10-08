"""OCR selection: fast Windows OCR, then shared Kafka, then local fallbacks."""

from __future__ import annotations

from .base import NullOcr, OcrBackend, OcrResult, join_blocks

__all__ = ["OcrBackend", "OcrResult", "NullOcr", "join_blocks", "select_ocr", "ocr_availability"]

ORDER = ["winocr", "family", "rapidocr", "tesseract"]


def _classes() -> dict[str, type[OcrBackend]]:
    from .family import FamilyOcr
    from .rapid import RapidOcr
    from .tesseract import TesseractOcr
    from .winocr_backend import WinOcr

    return {"rapidocr": RapidOcr, "winocr": WinOcr, "tesseract": TesseractOcr, "family": FamilyOcr}


def ocr_availability() -> dict[str, dict]:
    """For the settings page: which engines could run here and why not."""
    out = {}
    for name, cls in _classes().items():
        ok, reason = cls.available()
        out[name] = {"available": ok, "reason": reason}
    return out


def select_ocr(requested: str = "auto", language: str = "es", *, exclude: tuple[str, ...] = ()) -> tuple[OcrBackend, list[str]]:
    """Instantiate the requested engine or the first available one; returns (engine, notes)."""
    classes = _classes()
    notes: list[str] = []
    candidates = ORDER if requested == "auto" else [requested, *[n for n in ORDER if n != requested]]
    for name in candidates:
        if name in exclude:
            continue
        cls = classes.get(name)
        if cls is None:
            continue
        ok, reason = cls.available()
        if not ok:
            notes.append(f"{name}: {reason}")
            continue
        try:
            engine = cls(language) if name in ("winocr", "tesseract", "family") else cls()
            if name == "family" and requested == "auto":
                engine.allow_local_fallback = True
        except Exception as error:  # broken install
            notes.append(f"{name}: failed to start ({error})")
            continue
        if requested not in ("auto", name):
            notes.append(f"requested {requested} unavailable, using {name}")
        return engine, notes
    notes.append("no OCR engine available; frames are stored without text")
    return NullOcr(), notes
