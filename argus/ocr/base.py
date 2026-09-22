"""OCR backend interface and shared result types."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from ..store import Block


@dataclass
class OcrResult:
    blocks: list[Block] = field(default_factory=list)
    text: str = ""
    backend: str = ""


class OcrBackend:
    name = "base"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """(usable, reason). Must be cheap and never raise."""
        return False, "not implemented"

    def recognise(self, image: Image.Image) -> OcrResult:  # pragma: no cover - interface
        raise NotImplementedError


def join_blocks(blocks: list[Block], line_tolerance: int = 12) -> str:
    """Concatenate block texts in reading order: rows by y (with tolerance), then x."""
    ordered = sorted(blocks, key=lambda b: (b.y, b.x))
    lines: list[list[Block]] = []
    for block in ordered:
        if lines and abs(lines[-1][0].y - block.y) <= line_tolerance:
            lines[-1].append(block)
        else:
            lines.append([block])
    return "\n".join(" ".join(b.text for b in sorted(line, key=lambda b: b.x)) for line in lines)


def quad_to_box(points) -> tuple[int, int, int, int]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    x, y = min(xs), min(ys)
    return int(round(x)), int(round(y)), int(round(max(xs) - x)), int(round(max(ys) - y))


class NullOcr(OcrBackend):
    """Used when no OCR engine is importable: frames are stored, text stays empty."""

    name = "none"

    def __init__(self, reason: str = "no OCR backend available"):
        self.reason = reason

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return True, "always"

    def recognise(self, image: Image.Image) -> OcrResult:
        return OcrResult(backend=self.name)
