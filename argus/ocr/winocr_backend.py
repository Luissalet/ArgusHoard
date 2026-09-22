"""Windows.Media.Ocr through the `winocr` package (Windows 10/11 only, very fast).

Not verifiable off Windows: the result is read defensively (dict or WinRT object).
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

from PIL import Image

from ..store import Block
from .base import OcrBackend, OcrResult, join_blocks


def _load_onnxruntime_first() -> None:
    """Measured on Windows 11 / Python 3.13: importing `winocr` (WinRT) and then
    `onnxruntime` dies with an access violation, while the other order is fine.
    So whenever onnxruntime is installed it is imported before WinRT touches the
    process, even if this session never uses RapidOCR."""
    if importlib.util.find_spec("onnxruntime") is None:
        return
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # a broken onnxruntime must not take winocr down with it
        pass


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class WinOcr(OcrBackend):
    name = "winocr"

    def __init__(self, language: str = "es"):
        _load_onnxruntime_first()
        import winocr

        self._winocr = winocr
        self.language = language

    @classmethod
    def available(cls) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "winocr only works on Windows"
        if importlib.util.find_spec("winocr") is None:
            return False, "winocr is not installed (pip install -r requirements-windows.txt)"
        return True, "ok"

    def recognise(self, image: Image.Image) -> OcrResult:
        try:
            result = self._winocr.recognize_pil_sync(image.convert("RGB"), self.language)
        except Exception:
            # Language pack may be missing: retry with the system default (English pack is common).
            result = self._winocr.recognize_pil_sync(image.convert("RGB"), "en")
        blocks: list[Block] = []
        for line in _get(result, "lines", []) or []:
            words = _get(line, "words", []) or []
            rects = [_get(w, "bounding_rect") for w in words]
            rects = [r for r in rects if r is not None]
            text = " ".join(str(_get(w, "text", "")) for w in words).strip() or str(_get(line, "text", "")).strip()
            if not text:
                continue
            if rects:
                x = min(float(_get(r, "x", 0)) for r in rects)
                y = min(float(_get(r, "y", 0)) for r in rects)
                right = max(float(_get(r, "x", 0)) + float(_get(r, "width", 0)) for r in rects)
                bottom = max(float(_get(r, "y", 0)) + float(_get(r, "height", 0)) for r in rects)
                blocks.append(Block(text=text, x=int(x), y=int(y), w=int(right - x), h=int(bottom - y), conf=1.0))
            else:
                blocks.append(Block(text=text, x=0, y=len(blocks) * 20, w=image.width, h=20, conf=1.0))
        return OcrResult(blocks=blocks, text=join_blocks(blocks), backend=self.name)
