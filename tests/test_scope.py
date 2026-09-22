"""Capture scope (active monitor vs all), idle detection and session grouping."""

import time

from argus.capture.base import Backends, Monitor, WindowInfo
from argus.capture.fake import FakeCapture, FakeScript, FakeWindow, NullWindow
from argus.capture.fixtures import MULTI_MONITOR_SCENES, FixtureScene


def noon() -> float:
    return time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))


def multi(services, scenes=None):
    script = FakeScript(scenes or MULTI_MONITOR_SCENES)
    capture = FakeCapture(script)
    services.recorder.backends = Backends(capture, FakeWindow(script))
    return capture


def test_active_scope_captures_only_the_monitor_with_the_window(services):
    capture = multi(services)
    start = noon()
    results = [services.recorder.tick(now=start + i * 5) for i in range(6)]
    # editor (monitor 1) x2, navegador (monitor 2) x2, terminal (monitor 1) x2
    assert [r.active_monitor for r in results] == [1, 1, 2, 2, 1, 1]
    assert capture.grab_calls == [[1], [1], [2], [2], [1], [1]]
    frames = services.queries.timeline(None, None, None, None, 20, None, ascending=True)["frames"]
    assert [(f["app"], f["monitor"]) for f in frames] == [("editor", 1), ("navegador", 2), ("terminal", 1)]
    assert services.frames.frame_count() == 3  # one per scene, never the idle desktop


def test_all_scope_captures_every_monitor_and_tags_only_the_active_one(services):
    services.update_settings({"capture_scope": "all"})
    capture = multi(services)
    start = noon()
    first = services.recorder.tick(now=start)
    assert capture.grab_calls == [None] and sorted(first.monitors) == [1, 2]
    frames = services.queries.timeline(None, None, None, None, 20, None, ascending=True)["frames"]
    by_monitor = {f["monitor"]: f for f in frames}
    assert by_monitor[1]["app"] == "editor" and by_monitor[2]["app"] == ""  # the idle desktop carries no window
    second = services.recorder.tick(now=start + 5)
    assert second.stored == [] and len(second.extended) == 2  # both monitors unchanged


def test_unknown_window_falls_back_to_the_primary_monitor(services):
    script = FakeScript(MULTI_MONITOR_SCENES)
    capture = FakeCapture(script, monitors=[Monitor(1, 1920, 0, 1280, 720, False), Monitor(2, 0, 0, 1280, 720, True)])
    services.recorder.backends = Backends(capture, NullWindow())
    result = services.recorder.tick(now=noon())
    assert result.active_monitor == 2 and capture.grab_calls == [[2]]


def test_window_monitor_lookup():
    monitors = [Monitor(1, 0, 0, 1920, 1080, True), Monitor(2, 1920, 0, 1080, 1920)]
    assert WindowInfo(rect=(100, 100, 800, 600)).monitor_index(monitors) == 1
    assert WindowInfo(rect=(2000, 300, 2500, 900)).monitor_index(monitors) == 2
    assert WindowInfo(rect=(-500, -500, -100, -100)).monitor_index(monitors) is None
    assert WindowInfo().monitor_index(monitors) is None


def test_idle_since_tracks_the_repeated_frame_and_no_extra_ocr(services):
    static = [FixtureScene("editor", "notas.txt", ["Sin cambios"], repeat=1)]
    multi(services, static)
    start = noon()
    first = services.recorder.tick(now=start)
    assert first.stored and services.recorder.idle_since is None
    for i in range(1, 25):
        result = services.recorder.tick(now=start + i * 5)
        assert not result.stored
    assert services.recorder.idle_since == start
    assert services.ocr.depth <= 1 and services.frames.frame_count() == 1  # nothing new queued for OCR
    status = services.status()
    assert status["idle_since"] and status["idle_s"] >= 0 and status["capture_scope"] == "active"
    # a new screen ends the idle period
    multi(services, [FixtureScene("terminal", "Terminal", ["Otra cosa", "Traceback"], repeat=1)])
    assert services.recorder.tick(now=start + 25 * 5).stored
    assert services.recorder.idle_since is None


def test_sessions_group_consecutive_frames(services):
    multi(services)
    start = noon()
    for i in range(12):  # editor x2, navegador x2, terminal x2, editor x2, ... => 6 sessions
        services.recorder.tick(now=start + i * 5)
    sessions = services.queries.sessions(day=time.strftime("%Y-%m-%d", time.localtime(start)))
    assert [s["app"] for s in sessions] == ["editor", "navegador", "terminal"] * 2
    first = sessions[0]
    assert first["count"] == 1 and first["duration_s"] == 10 and first["first_id"] == first["last_id"]
    assert first["thumbs"] == [first["first_id"]]
    assert sessions[1]["start_at"] == start + 10 and sessions[1]["end_at"] == start + 20
    assert sum(s["duration_s"] for s in sessions) == 12 * 5
    assert services.queries.sessions(day=time.strftime("%Y-%m-%d", time.localtime(start)), app="terminal")[0]["app"] == "terminal"
