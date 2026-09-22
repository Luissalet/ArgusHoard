import pytest

from argus.capture.fixtures import DEFAULT_SCENES, render_screen
from argus.ocr import select_ocr
from argus.ocr.base import join_blocks
from argus.ocr.rapid import RapidOcr
from argus.store import Block


@pytest.fixture(scope="module")
def rapid():
    ok, reason = RapidOcr.available()
    if not ok:
        pytest.skip(reason)
    return RapidOcr()


def test_rapidocr_reads_rendered_text(rapid):
    image = render_screen(["Presupuesto mensual 2026", "Traceback: KeyError missing_value"], title_bar="Terminal")
    result = rapid.recognise(image)
    text = result.text.lower()
    assert "presupuesto" in text and "mensual" in text and "2026" in text
    assert "traceback" in text and "keyerror" in text
    assert all(b.w > 0 and b.h > 0 and 0 <= b.conf <= 1 for b in result.blocks)
    assert result.backend == "rapidocr"


def test_rapidocr_reads_every_fixture_scene(rapid):
    for scene in DEFAULT_SCENES:
        text = rapid.recognise(scene.render()).text.lower()
        first_words = [line.split()[0].lower() for line in scene.lines]
        assert all(word in text for word in first_words), (scene.app, text)


def test_select_ocr_falls_back_to_rapidocr():
    engine, notes = select_ocr("winocr")  # Windows-only engine requested off Windows
    assert engine.name in ("rapidocr", "tesseract")
    assert any("winocr" in n for n in notes)


def test_join_blocks_reading_order():
    blocks = [Block("mundo", 120, 10, 60, 20), Block("hola", 10, 12, 60, 20), Block("segunda", 10, 60, 80, 20)]
    assert join_blocks(blocks) == "hola mundo\nsegunda"
