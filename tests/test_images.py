from PIL import ImageDraw

from argus.capture.fixtures import render_screen
from argus.images import changed_cells, dhash, fit_width, hamming, is_near_duplicate, signature


def screen(lines):
    return render_screen(lines, size=(1920, 1080), font_size=16)  # realistic: 1080p, small text


def test_dhash_is_stable_and_scale_invariant():
    image = screen(["Lista de la compra", "Pan integral"])
    assert dhash(image) == dhash(image.copy())
    assert len(dhash(image)) == 64
    assert hamming(dhash(image), dhash(fit_width(image, 960))) <= 6


def test_caret_and_clock_are_duplicates_but_new_text_is_not():
    base = screen(["Lista de la compra", "Pan integral"])
    caret = base.copy()
    ImageDraw.Draw(caret).rectangle([300, 400, 301, 416], fill="black")
    clock = base.copy()
    ImageDraw.Draw(clock).text((1850, 14), "12:35", fill="white")
    new_line = screen(["Lista de la compra", "Pan integral", "Tomates"])
    scrolled = screen(["Pan integral", "Tomates", "Leche"])
    other = render_screen(["Traceback (most recent call last):", "KeyError", "Proceso terminado"], size=(1920, 1080), title_bar="Terminal")

    threshold = 8
    ref = signature(base)
    assert is_near_duplicate(ref, signature(caret), threshold)
    assert is_near_duplicate(ref, signature(clock), threshold)
    assert not is_near_duplicate(ref, signature(new_line), threshold)
    assert not is_near_duplicate(ref, signature(scrolled), threshold)
    assert not is_near_duplicate(ref, signature(other), threshold)
    assert changed_cells(ref, signature(caret)) < changed_cells(ref, signature(new_line)) < changed_cells(ref, signature(other))


def test_threshold_semantics():
    a = signature(screen(["a"]))
    assert changed_cells(a, a) == 0
    assert is_near_duplicate(a, a, threshold=1)
    assert not is_near_duplicate(a, a, threshold=0)  # strictly below
    assert not is_near_duplicate(None, a, threshold=2000)
