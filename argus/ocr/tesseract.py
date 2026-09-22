"""Tesseract through `pytesseract` (only if importable and the binary is present)."""

from __future__ import annotations

import importlib.util

from PIL import Image

from ..store import Block
from .base import OcrBackend, OcrResult, join_blocks

LANG_MAP = {"es": "spa", "en": "eng", "fr": "fra", "de": "deu", "pt": "por", "it": "ita", "ca": "cat"}


class TesseractOcr(OcrBackend):
    name = "tesseract"

    def __init__(self, language: str = "es"):
        import pytesseract

        self._pt = pytesseract
        self.lang = LANG_MAP.get(language.lower()[:2], language)

    @classmethod
    def available(cls) -> tuple[bool, str]:
        if importlib.util.find_spec("pytesseract") is None:
            return False, "pytesseract is not installed"
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
        except Exception as error:
            return False, f"tesseract binary not usable: {error}"
        return True, "ok"

    def recognise(self, image: Image.Image) -> OcrResult:
        try:
            data = self._pt.image_to_data(image.convert("RGB"), lang=self.lang, output_type=self._pt.Output.DICT)
        except self._pt.TesseractError:
            data = self._pt.image_to_data(image.convert("RGB"), output_type=self._pt.Output.DICT)
        lines: dict[tuple, list] = {}
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            if not word or float(data["conf"][i]) < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(i)
        blocks: list[Block] = []
        for indices in lines.values():
            xs = [data["left"][i] for i in indices]
            ys = [data["top"][i] for i in indices]
            rights = [data["left"][i] + data["width"][i] for i in indices]
            bottoms = [data["top"][i] + data["height"][i] for i in indices]
            conf = sum(float(data["conf"][i]) for i in indices) / len(indices) / 100
            text = " ".join(data["text"][i].strip() for i in indices)
            blocks.append(Block(text, min(xs), min(ys), max(rights) - min(xs), max(bottoms) - min(ys), round(conf, 3)))
        return OcrResult(blocks=blocks, text=join_blocks(blocks), backend=self.name)
