"""Kafka's OCR engine through the family hub: shared before loading another OCR model.

Used after the fast Windows engine in auto mode (or when `ocr_backend` is "family"). The frame is written
to a temporary PNG for the service (it takes paths), removed right after, and never leaves the machine.
"""

from __future__ import annotations

import logging
import os
import tempfile

from PIL import Image

from ..hoard_link import fam_docs
from ..store import Block
from .base import OcrBackend, OcrResult, join_blocks, quad_to_box

log = logging.getLogger("argus.ocr")


class FamilyOcr(OcrBackend):
    name = "family"

    def __init__(self, language: str = "es"):
        self.lang = (language or "es").lower()[:2]
        self.allow_local_fallback = False
        self._fallback = None

    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            if fam_docs.available():
                return True, "ok"
        except Exception as error:  # noqa: BLE001 - never raises, by contract
            return False, f"family OCR not reachable: {error}"
        return False, "the family OCR service (Kafka's Hoard through the hub) is not reachable"

    def recognise(self, image: Image.Image) -> OcrResult:
        handle, path = tempfile.mkstemp(prefix="argus-ocr-", suffix=".png")
        os.close(handle)
        try:
            image.convert("RGB").save(path, "PNG")
            got = fam_docs.ocr_image(path, lang=self.lang, blocks=True)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if not got.get("ok"):
            log.debug("family OCR failed: %s", got.get("error") or got.get("kind"))
            if self.allow_local_fallback and got.get("kind") in ("hub_down", "app_down", "app_missing", "tool_missing"):
                if self._fallback is None:
                    from . import select_ocr
                    self._fallback, _ = select_ocr("auto", self.lang, exclude=("family",))
                return self._fallback.recognise(image)
            return OcrResult(backend=self.name)
        self._fallback = None  # recovered service: release the local fallback model
        blocks: list[Block] = []
        for item in got.get("blocks") or []:
            text = str(item.get("text") or "").strip()
            box = item.get("box")
            if not text or not box:
                continue
            try:
                x, y, w, h = quad_to_box(box)
            except (TypeError, ValueError, IndexError):
                continue
            score = item.get("score")
            blocks.append(Block(text, x, y, w, h, round(float(score), 3) if isinstance(score, (int, float)) else 0.0))
        text = join_blocks(blocks) if blocks else str(got.get("text") or "").strip()
        return OcrResult(blocks=blocks, text=text, backend=self.name)
