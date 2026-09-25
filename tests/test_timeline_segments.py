"""screen_timeline folds consecutive frames of one app + window into segments."""
from argus.agent_tools import _segments


def frame(i, app, title, ts, dur=5.0, excerpt="x"):
    return {"id": i, "captured_at": f"t{ts}", "until_at": f"u{ts}", "duration_s": dur, "app": app,
            "window_title": title, "excerpt": excerpt, "_ts": float(ts)}


def test_consecutive_frames_fold_into_one_segment():
    frames = [frame(5, "code", "a.py", 50), frame(4, "code", "a.py", 40, excerpt="longer text"),
              frame(3, "chrome", "docs", 30), frame(2, "code", "a.py", 20), frame(1, "code", "a.py", 10)]
    segs, cut = _segments(frames, 10)
    assert [s["app"] for s in segs] == ["code", "chrome", "code"]
    assert segs[0]["frames"] == 2 and segs[0]["frame_ids"] == [5, 4] and segs[0]["duration_s"] == 10.0
    assert segs[0]["from"] == "t40" and segs[0]["until"] == "u50" and segs[0]["excerpt"] == "longer text"
    assert cut is None


def test_limit_returns_a_cursor_at_the_oldest_frame_used():
    frames = [frame(i, f"app{i % 3}", "w", i * 10) for i in range(9, 0, -1)]
    segs, cut = _segments(frames, 2)
    assert len(segs) == 2 and cut == segs[-1]["_ts"]


def test_frame_ids_are_capped():
    frames = [frame(i, "code", "a.py", i) for i in range(20, 0, -1)]
    segs, _ = _segments(frames, 5)
    assert len(segs) == 1 and segs[0]["frames"] == 20 and len(segs[0]["frame_ids"]) == 5
