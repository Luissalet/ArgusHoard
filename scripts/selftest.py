"""One real capture on this machine: grab the screen, read the active window, OCR it.

Run it on the owner's PC to verify the platform backends without starting the app:

    venv\\Scripts\\python scripts\\selftest.py            # default OCR (winocr if installed, else rapidocr)
    venv\\Scripts\\python scripts\\selftest.py rapidocr   # force one engine
    venv\\Scripts\\python scripts\\selftest.py --fake     # use fixture frames (works anywhere)

It prints the window, the OCR text, timings and writes selftest.webp next to
this script. Nothing is stored in the database.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from argus.capture import select_backends  # noqa: E402
from argus.capture.base import primary_index  # noqa: E402
from argus.images import changed_cells, dhash, save_frame_images, signature  # noqa: E402
from argus.ocr import ocr_availability, select_ocr  # noqa: E402
from argus.settings import Settings  # noqa: E402


def main(argv: list[str]) -> int:
    fake = "--fake" in argv
    requested = next((a for a in argv if not a.startswith("-")), "auto")
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    print("OCR engines:", ", ".join(f"{k} ({'ok' if v['available'] else v['reason']})" for k, v in ocr_availability().items()))

    started = time.perf_counter()
    backends = select_backends("fake" if fake else "auto", "fake" if fake else "auto")
    for note in backends.notes:
        print("note:", note)
    print(f"capture backend: {backends.capture.name}, window backend: {backends.window.name}")

    window = backends.window.active()
    print(f"active window: app={window.app!r} title={window.title!r} pid={window.pid} rect={window.rect}")
    try:
        monitors = backends.capture.monitors()
        print("monitors: " + ", ".join(f"#{m.index} {m.width}x{m.height} at ({m.left},{m.top}){' primary' if m.primary else ''}" for m in monitors))
        active = window.monitor_index(monitors)
        print(f"active window is on monitor: {active} (capture_scope=active would grab only #{active or primary_index(monitors)})")
        grabs = backends.capture.grab(None)  # every monitor, to time the worst case
    except Exception as error:
        print(f"capture FAILED: {error}")
        return 1
    grab_ms = (time.perf_counter() - started) * 1000
    print(f"captured {len(grabs)} monitor(s) in {grab_ms:.0f} ms: " + ", ".join(f"#{g.monitor} {g.image.width}x{g.image.height}" for g in grabs))
    t0 = time.perf_counter()
    only = backends.capture.grab([active or primary_index(monitors)])
    print(f"captured the active monitor alone in {(time.perf_counter() - t0) * 1000:.0f} ms")

    grab = next((g for g in grabs if g.monitor == active), grabs[0])
    t0 = time.perf_counter()
    sig = signature(grab.image)
    print(f"signature {sig.shape} in {(time.perf_counter() - t0) * 1000:.1f} ms; dhash {dhash(grab.image)[:16]}…")
    t0 = time.perf_counter()
    second = only[0].image
    print(f"cells changed between two consecutive grabs: {changed_cells(sig, signature(second))} (threshold default {Settings().dedupe_threshold})")

    out = Path(__file__).resolve().parent / "selftest.webp"
    thumb = Path(__file__).resolve().parent / "selftest.t.webp"
    size = save_frame_images(grab.image, out, thumb, 1280, 320)
    print(f"saved {out.name} + thumbnail ({size / 1024:.0f} KB)")

    t0 = time.perf_counter()
    engine, notes = select_ocr(requested, "es")
    for note in notes:
        print("ocr note:", note)
    print(f"ocr engine: {engine.name} (ready in {(time.perf_counter() - t0) * 1000:.0f} ms)")
    t0 = time.perf_counter()
    result = engine.recognise(grab.image)
    ocr_ms = (time.perf_counter() - t0) * 1000
    print(f"ocr: {len(result.blocks)} blocks in {ocr_ms:.0f} ms")
    print("-" * 60)
    print(result.text[:4000] or "(no text recognised)")
    print("-" * 60)
    backends.capture.close()
    return 0 if grabs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
