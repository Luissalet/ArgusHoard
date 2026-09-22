"""Rendered-text fixtures: fictional screens drawn with Pillow so OCR has something to read."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def load_font(size: int = 28) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def render_screen(lines: list[str], size: tuple[int, int] = (1280, 720), title_bar: str = "", font_size: int = 28) -> Image.Image:
    """A fake window: light chrome, a title bar and left-aligned lines of text."""
    image = Image.new("RGB", size, "#f4f4f6")
    draw = ImageDraw.Draw(image)
    font = load_font(font_size)
    small = load_font(max(14, font_size - 8))
    draw.rectangle([0, 0, size[0], 44], fill="#2b2b33")
    if title_bar:
        draw.text((16, 10), title_bar, fill="#ffffff", font=small)
    draw.rectangle([24, 70, size[0] - 24, size[1] - 24], fill="#ffffff", outline="#d8d8de")
    y = 96
    for line in lines:
        draw.text((48, y), line, fill="#1c1c22", font=font)
        y += int(font_size * 1.8)
    return image


@dataclass
class FixtureScene:
    app: str
    title: str
    lines: list[str]
    repeat: int = 1  # how many consecutive ticks this scene stays on screen
    size: tuple[int, int] = (1280, 720)
    image: Image.Image | None = field(default=None, repr=False)

    def render(self) -> Image.Image:
        if self.image is None:
            self.image = render_screen(self.lines, self.size, f"{self.title} - {self.app}")
        return self.image


DEFAULT_SCENES: list[FixtureScene] = [
    FixtureScene("editor", "notas.txt - Editor de texto", ["Lista de la compra", "Pan integral y tomates", "Llamar al fontanero el martes"], repeat=3),
    FixtureScene("navegador", "Receta de paella - Navegador", ["Receta de paella valenciana", "Arroz bomba 400 gramos", "Azafran y pimenton dulce"], repeat=2),
    FixtureScene("terminal", "Terminal", ["Traceback (most recent call last):", "KeyError: 'presupuesto'", "Proceso terminado con error 1"], repeat=2),
    FixtureScene("hoja", "Presupuesto 2026 - Hojas", ["Presupuesto mensual 2026", "Alquiler 850", "Comida 320", "Transporte 60"], repeat=4),
    FixtureScene("banco", "Banco Ficticio - Navegador", ["Cuenta corriente", "Saldo disponible 1234", "Movimientos recientes"], repeat=2),
]
