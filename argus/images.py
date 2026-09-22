"""Perceptual hashing, change detection and WebP storage for captured frames.

Two measures, both Pillow/numpy only:
- `dhash` (16x16 difference hash, 256 bits) is stored per frame as `phash`.
- `signature` (a 384x216 grey grid, 5x5 px cells at 1080p) is kept in memory for the previous frame of
  each monitor; `changed_cells` counts cells whose grey level moved by more than
  `LEVEL`. A whole-screen hash is too coarse for text: a caret blink and a new
  line of text differ by the same 1-2 bits, whereas on the grid a caret or the
  clock changes 4-10 cells and a new line of 16 px text 25+ (measured on
  fixtures with both DejaVu and Segoe UI; Segoe's thinner strokes are why the
  grid is this fine and the level this low).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

HASH_SIZE = 16  # 16x16 differences -> 256 bits
GRID = (384, 216)
LEVEL = 12  # grey-level delta that counts as a changed cell


def dhash(image: Image.Image, size: int = HASH_SIZE) -> str:
    small = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = np.asarray(small, dtype=np.int16)
    bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        return max(len(a), len(b)) * 4
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def signature(image: Image.Image, grid: tuple[int, int] = GRID) -> np.ndarray:
    """Grey grid used for change detection (about 3 ms for a 1080p frame)."""
    return np.asarray(image.convert("L").resize(grid, Image.Resampling.BOX), dtype=np.int16)


def changed_cells(previous: np.ndarray, current: np.ndarray, level: int = LEVEL) -> int:
    if previous.shape != current.shape:
        return current.size
    return int((np.abs(previous - current) > level).sum())


def is_near_duplicate(previous: np.ndarray | None, current: np.ndarray, threshold: int) -> bool:
    """True when fewer than `threshold` grid cells changed (strictly below)."""
    if previous is None:
        return False
    return changed_cells(previous, current) < threshold


def fit_width(image: Image.Image, max_width: int) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / image.width
    return image.resize((max_width, max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)


def frame_paths(frames_dir: Path, day: str, frame_id: int) -> tuple[Path, Path]:
    """`<frames_dir>/YYYY/MM/DD/<id>.webp` and its `<id>.t.webp` thumbnail."""
    year, month, dom = day.split("-")
    folder = frames_dir / year / month / dom
    return folder / f"{frame_id}.webp", folder / f"{frame_id}.t.webp"


def save_frame_images(
    image: Image.Image,
    image_path: Path,
    thumb_path: Path,
    max_width: int = 1280,
    thumb_width: int = 320,
    quality: int = 80,
) -> int:
    """Write the main WebP and the thumbnail; return total bytes on disk."""
    image_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    main = fit_width(rgb, max_width)
    main.save(image_path, "WEBP", quality=quality, method=4)
    thumb = fit_width(main, thumb_width)
    thumb.save(thumb_path, "WEBP", quality=max(40, quality - 15), method=4)
    return image_path.stat().st_size + thumb_path.stat().st_size


def remove_images(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            continue
        parent = path.parent
        # prune empty day/month/year folders, never past the frames root
        for _ in range(3):
            try:
                if any(parent.iterdir()):
                    break
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
