"""RapidOCR (ONNX runtime, CPU) — the cross-platform default."""

from __future__ import annotations

import importlib.util

import numpy as np
from PIL import Image

from ..store import Block
from .base import OcrBackend, OcrResult, join_blocks, quad_to_box


class RapidOcr(OcrBackend):
    name = "rapidocr"

    # Two packages expose the same engine: `rapidocr` (v2+, Python 3.13 wheels)
    # and the older `rapidocr-onnxruntime` (no 3.13 wheels). Prefer the new one.
    @staticmethod
    def _package() -> str | None:
        for name in ("rapidocr", "rapidocr_onnxruntime"):
            if importlib.util.find_spec(name) is not None:
                return name
        return None

    def __init__(self):
        package = self._package()
        if package == "rapidocr":
            from rapidocr import RapidOCR
        else:
            from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        self._modern = package == "rapidocr"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        if cls._package() is None:
            return False, "rapidocr is not installed (pip install rapidocr)"
        return True, "ok"

    def _items(self, array):
        if self._modern:
            output = self._engine(array)
            boxes = getattr(output, "boxes", None)
            if boxes is None:
                return []
            return list(zip(boxes, output.txts, output.scores))
        result, _elapse = self._engine(array)
        return list(result or [])

    def recognise(self, image: Image.Image) -> OcrResult:
        array = np.asarray(image.convert("RGB"))
        blocks: list[Block] = []
        for item in self._items(array):
            quad, text, conf = item[0], str(item[1]).strip(), float(item[2])
            if not text:
                continue
            x, y, w, h = quad_to_box(quad)
            blocks.append(Block(text=text, x=x, y=y, w=w, h=h, conf=round(conf, 3)))
        return OcrResult(blocks=blocks, text=join_blocks(blocks), backend=self.name)
