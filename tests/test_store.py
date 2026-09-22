import time

from argus.capture.fixtures import render_screen
from argus.images import dhash
from argus.store import Block


def add_frame(svc, at, app, title, lines, interval=5, monitor=1):
    image = render_screen(lines, title_bar=title)
    frame_id = svc.frames.insert_frame(
        image, captured_at=at, interval_s=interval, monitor=monitor, app=app, window_title=title, phash=dhash(image)
    )
    blocks = [Block(line, 48, 96 + 50 * i, 400, 30, 0.9) for i, line in enumerate(lines)]
    svc.frames.set_ocr_result(frame_id, blocks, "\n".join(lines), 12, "stub")
    return frame_id


def test_search_ranks_and_snippets(services):
    now = time.time()
    a = add_frame(services, now - 300, "editor", "notas.txt", ["Lista de la compra", "Pan integral y tomates"])
    b = add_frame(services, now - 200, "terminal", "Terminal", ["Traceback (most recent call last)", "KeyError: 'presupuesto'"])
    c = add_frame(services, now - 100, "hoja", "Presupuesto 2026", ["Presupuesto mensual", "Alquiler 850"])
    result = services.queries.search("presupuesto", None, None, None, 10)
    ids = [h["id"] for h in result["hits"]]
    assert set(ids) == {b, c}
    assert ids[0] == c  # window title weight pushes the spreadsheet first
    assert "[Presupuesto]" in result["hits"][0]["snippet"] or "[presupuesto]" in result["hits"][0]["snippet"]
    assert services.queries.search("tomates", None, None, None, 10)["hits"][0]["id"] == a
    assert services.queries.search("integral tomates", None, None, None, 10)["hits"][0]["id"] == a
    assert services.queries.search("integral pimenton", None, None, None, 10)["hits"] == []
    # accents are folded and odd characters do not break FTS syntax
    assert services.queries.search("compra \"quoted\" AND OR (x)", None, None, None, 10)["hits"] == []
    assert services.queries.search("lísta", None, None, None, 10)["hits"][0]["id"] == a
    # app filter and time filter
    assert [h["id"] for h in services.queries.search("presupuesto", None, None, "terminal", 10)["hits"]] == [b]
    assert [h["id"] for h in services.queries.search("presupuesto", now - 150, None, None, 10)["hits"]] == [c]


def test_timeline_durations_and_dedupe(services):
    # a fixed local noon: the test adds an hour and must stay on the same day
    start = time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1)) - 600
    stored = []
    for index in range(6):
        stored.extend(services.recorder.tick(now=start + index * 5).stored)
    # scene 1 repeats 3 ticks, scene 2 repeats 2, then scene 3 starts: 3 distinct frames
    assert len(stored) == 3
    frames = services.queries.timeline(None, None, None, None, 10, None, ascending=True)["frames"]
    assert [f["duration_s"] for f in frames] == [15.0, 10.0, 5.0]
    assert frames[0]["app"] == "editor" and frames[1]["app"] == "navegador"
    # a long gap means a new frame even if the screen looks the same
    stored_after_gap = services.recorder.tick(now=start + 3600).stored
    assert stored_after_gap
    stats = services.frames.today_stats(now=start + 3600)
    assert stats["ticks"] == 7 and stats["frames"] == 4


def test_exclusions_record_hidden_ticks_only(services):
    services.exclusions.add("app", "editor")
    result = services.recorder.tick(now=time.time())
    assert result.hidden and not result.stored
    assert services.frames.frame_count() == 0
    assert services.frames.today_stats()["hidden"] == 1
    services.exclusions.remove(services.exclusions.list()[0].id)
    assert services.recorder.tick(now=time.time()).stored


def test_apps_and_days(services):
    now = time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))  # local noon: frames must stay on one day
    add_frame(services, now - 100, "editor", "notas.txt", ["a"], interval=30)
    add_frame(services, now - 60, "editor", "otro.txt", ["b"], interval=20)
    add_frame(services, now - 30, "navegador", "Receta", ["c"], interval=10)
    apps = services.queries.apps(None, None)
    assert apps["total_seconds"] == 60
    assert apps["apps"][0]["app"] == "editor" and apps["apps"][0]["seconds"] == 50
    assert apps["apps"][0]["top_windows"][0]["window_title"] == "notas.txt"
    days = services.queries.days()
    assert len(days) == 1 and days[0]["frames"] == 3 and days[0]["seconds"] == 60


def test_retention_janitor_and_storage_cap(services):
    now = time.time()
    old = add_frame(services, now - 40 * 86400, "editor", "viejo", ["viejo"])
    fresh = add_frame(services, now - 60, "editor", "nuevo", ["nuevo"])
    old_paths = services.frames.image_file(old)
    assert old_paths[0].exists()
    services.settings.update({"retention_days": 30})
    report = services.janitor.run(now=now)
    assert report["deleted_by_age"] == 1
    assert services.queries.frame(old) is None and services.queries.frame(fresh) is not None
    assert not old_paths[0].exists() and not old_paths[1].exists()
    assert services.queries.search("viejo", None, None, None, 5)["hits"] == []
    # storage cap: force a tiny cap by lowering the frame sizes' budget
    for i in range(4):
        add_frame(services, now - 50 + i, "editor", f"f{i}", [f"frame {i}"])
    usage = services.frames.disk_usage()
    assert usage > 0
    services.frames.delete_frames(services.frames.oldest_frames_over_cap(usage // 2))
    assert services.frames.disk_usage() <= usage // 2 + 1
    assert services.frames.frame_count() < 5


def test_delete_range(services):
    now = time.time()
    a = add_frame(services, now - 3000, "editor", "a", ["a"])
    b = add_frame(services, now - 1000, "editor", "b", ["b"])
    c = add_frame(services, now - 10, "editor", "c", ["c"])
    deleted = services.janitor.delete_range(now - 2000, now - 500)
    assert deleted == 1
    assert services.queries.frame(b) is None
    assert services.queries.frame(a) and services.queries.frame(c)


def test_pending_frames_are_ocrd_after_restart(services):
    """Frames stored before a crash get OCR'd from the WebP on disk, blocks scaled to original size."""
    image = render_screen(["Recuperar despues de reiniciar"], size=(1920, 1080), font_size=40)
    frame_id = services.frames.insert_frame(
        image, captured_at=time.time(), interval_s=5, monitor=1, app="editor", window_title="t", phash=dhash(image)
    )
    assert services.frames.pending_frames() == [frame_id]
    services.ocr.process_now(frame_id)  # nothing cached in memory: falls back to the stored file
    frame = services.queries.frame(frame_id)
    assert frame["ocr_status"] == "done" and "recuperar" in frame["text"].lower()
    assert frame["blocks"] and frame["blocks"][0]["w"] > 400  # scaled back to 1920-wide coordinates
