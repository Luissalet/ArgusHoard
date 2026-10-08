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
    """An engine that cannot run here is skipped with a note; the request is
    still honoured where it can be (winocr on Windows with the package)."""
    from argus.ocr.winocr_backend import WinOcr

    engine, notes = select_ocr("winocr")
    if WinOcr.available()[0]:
        assert engine.name == "winocr" and notes == []
    else:
        assert engine.name in ("rapidocr", "tesseract")
        assert any("winocr" in n for n in notes)


def test_join_blocks_reading_order():
    blocks = [Block("mundo", 120, 10, 60, 20), Block("hola", 10, 12, 60, 20), Block("segunda", 10, 60, 80, 20)]
    assert join_blocks(blocks) == "hola mundo\nsegunda"


def _png_boxes():
    return [{"text": "hola", "box": [[10, 12], [70, 12], [70, 32], [10, 32]], "score": 0.97},
            {"text": "mundo", "box": [[120, 10], [180, 10], [180, 30], [120, 30]], "score": 0.9},
            {"text": "", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "score": 1.0}]


def test_family_ocr_reads_through_the_hub_and_removes_its_temp_file(monkeypatch):
    from pathlib import Path

    from PIL import Image

    from argus.ocr.family import FamilyOcr

    seen = {}

    def fake(path, *, lang="es", blocks=False, timeout_s=120.0):
        seen.update(path=path, lang=lang, blocks=blocks, existed=Path(path).is_file())
        return {"ok": True, "text": "hola mundo", "blocks": _png_boxes(), "backend": "rapidocr"}

    monkeypatch.setattr("argus.ocr.family.fam_docs.ocr_image", fake)
    result = FamilyOcr("es").recognise(Image.new("RGB", (200, 50), "white"))
    assert result.backend == "family" and result.text == "hola mundo"
    assert [(b.text, b.x, b.y, b.w, b.h) for b in result.blocks] == [("hola", 10, 12, 60, 20), ("mundo", 120, 10, 60, 20)]
    assert seen["lang"] == "es" and seen["blocks"] and seen["existed"]
    assert not Path(seen["path"]).exists()


def test_family_ocr_failure_gives_an_empty_result(monkeypatch):
    from PIL import Image

    from argus.ocr.family import FamilyOcr

    monkeypatch.setattr("argus.ocr.family.fam_docs.ocr_image", lambda *a, **k: {"ok": False, "kind": "down", "error": "hub down"})
    result = FamilyOcr().recognise(Image.new("RGB", (20, 20), "white"))
    assert result.text == "" and result.blocks == [] and result.backend == "family"


def test_select_ocr_can_use_the_family_service_when_local_engines_are_absent(monkeypatch):
    from argus.ocr import rapid, tesseract, winocr_backend
    from argus.ocr.family import FamilyOcr

    for cls in (rapid.RapidOcr, tesseract.TesseractOcr, winocr_backend.WinOcr):
        monkeypatch.setattr(cls, "available", classmethod(lambda c: (False, "off")))
    monkeypatch.setattr(FamilyOcr, "available", classmethod(lambda c: (True, "ok")))
    engine, notes = select_ocr("auto")
    assert engine.name == "family" and len(notes) == 1
    monkeypatch.setattr(FamilyOcr, "available", classmethod(lambda c: (False, "hub down")))
    engine, notes = select_ocr("auto")
    assert engine.name == "none" and any("family" in n for n in notes)


def test_auto_shares_kafka_before_loading_another_ocr_model(monkeypatch):
    from argus.ocr import rapid, winocr_backend
    from argus.ocr.family import FamilyOcr
    monkeypatch.setattr(winocr_backend.WinOcr, "available", classmethod(lambda c: (False, "off")))
    monkeypatch.setattr(FamilyOcr, "available", classmethod(lambda c: (True, "ok")))
    monkeypatch.setattr(rapid.RapidOcr, "available", classmethod(lambda c: pytest.fail("do not load another OCR model")))
    engine, notes = select_ocr("auto")
    assert engine.name == "family"


def test_fast_windows_ocr_still_wins_over_network_roundtrip(monkeypatch):
    from argus.ocr import winocr_backend
    from argus.ocr.family import FamilyOcr
    monkeypatch.setattr(winocr_backend.WinOcr, "available", classmethod(lambda c: (True, "ok")))
    monkeypatch.setattr(winocr_backend.WinOcr, "__init__", lambda self, lang: None)
    monkeypatch.setattr(FamilyOcr, "available", classmethod(lambda c: pytest.fail("Windows does not need a model load")))
    assert select_ocr("auto")[0].name == "winocr"


def test_auto_family_ocr_falls_back_on_service_outage_but_never_on_auth_failure(monkeypatch):
    from PIL import Image
    from argus.ocr.family import FamilyOcr
    from argus.ocr.base import OcrResult
    selected = []
    class Local:
        def recognise(self, image):
            return OcrResult(text="local evidence", backend="fixture")
    def choose(*a, **kw):
        selected.append(kw)
        assert kw["exclude"] == ("family",)
        return Local(), []
    monkeypatch.setattr("argus.ocr.select_ocr", choose)
    monkeypatch.setattr("argus.ocr.family.fam_docs.ocr_image", lambda *a, **kw: {"ok": False, "kind": "hub_down"})
    engine = FamilyOcr()
    engine.allow_local_fallback = True
    image = Image.new("RGB", (20, 20), "white")
    assert engine.recognise(image).text == "local evidence"
    assert engine.recognise(image).backend == "fixture" and len(selected) == 1
    monkeypatch.setattr("argus.ocr.family.fam_docs.ocr_image", lambda *a, **kw: {"ok": False, "kind": "auth"})
    assert engine.recognise(image).text == "" and len(selected) == 1
    monkeypatch.setattr("argus.ocr.family.fam_docs.ocr_image", lambda *a, **kw: {"ok": True, "text": "shared evidence"})
    assert engine.recognise(image).text == "shared evidence" and engine._fallback is None
