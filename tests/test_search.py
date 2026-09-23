"""Search ranking (title beats body, ranks are real negatives even when FTS5's IDF clamps) and moment grouping."""

import time

from argus.capture.fixtures import render_screen
from argus.images import dhash
from argus.search import Candidate, group_moments, query_terms, tokens
from argus.store import Block

IMAGE = render_screen(["x"])
PHASH = dhash(IMAGE)


def add(svc, at, app, title, text, interval=5):
    fid = svc.frames.insert_frame(IMAGE, captured_at=at, interval_s=interval, monitor=1, app=app, window_title=title, phash=PHASH)
    svc.frames.set_ocr_result(fid, [Block(text, 0, 0, 10, 10)], text, 1, "stub")
    return fid


def noon():
    return time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))


def test_title_hit_outranks_single_body_mention_with_real_negative_ranks(services):
    t = noon()
    filler = "archivo editar ver ayuda terminal proyecto codigo linea error ventana " * 20
    body = add(services, t - 3000, "code", "main.py - Editor", filler + " plugins " + filler)
    title = add(services, t - 2000, "chrome", "plugins - Ajustes", filler)
    add(services, t - 1000, "chrome", "otra cosa", filler)
    result = services.queries.search("plugins", None, None, None, 10)
    ids = [h["id"] for h in result["hits"]]
    assert ids == [title, body]
    assert all(h["rank"] < 0 for h in result["hits"])
    assert result["hits"][0]["rank"] < result["hits"][1]["rank"] < -0.01  # clearly separated, not -0.0


def test_ranks_stay_meaningful_when_the_term_is_on_most_frames(services):
    """FTS5 clamps IDF to 1e-6 once a term is on more than half the rows; our rescoring must not."""
    t = noon()
    for i in range(12):  # twelve frames all mentioning the term in the body
        add(services, t - 5000 + i * 5, "code", f"tab {i} - Editor", f"linea {i} plugins instalados y mas plugins")
    title = add(services, t - 100, "chrome", "plugins - Ajustes", "sin nada")
    result = services.queries.search("plugins", None, None, None, 5)
    assert result["hits"][0]["id"] == title
    assert result["hits"][0]["rank"] < -0.2
    assert all(h["rank"] <= -0.05 for h in result["hits"])  # none rounds to -0.0
    assert result["hits"][0]["rank"] < result["hits"][1]["rank"]


def test_consecutive_identical_hits_collapse_into_moments(services):
    t = noon()
    text = "Traceback (most recent call last): KeyError plugins"
    run1 = [add(services, t - 3600 + i * 5, "terminal", "Terminal", text) for i in range(10)]  # one moment
    run2 = [add(services, t - 1800 + i * 5, "terminal", "Terminal", text) for i in range(10)]  # 20 min later: new moment
    other = add(services, t - 1700, "chrome", "plugins - Docs", "la pagina de plugins")
    result = services.queries.search("plugins", None, None, None, 10)
    assert result["frames_total"] == 21 and result["moments_total"] == 3
    moments = {h["window_title"]: h for h in result["hits"]}
    assert moments["plugins - Docs"]["count"] == 1 and moments["plugins - Docs"]["frame_ids"] == [other]
    terminal = [h for h in result["hits"] if h["app"] == "terminal"]
    assert [m["count"] for m in terminal] == [10, 10]
    assert sorted(terminal[0]["frame_ids"] + terminal[1]["frame_ids"]) == sorted(run1 + run2)
    assert terminal[0]["frame_ids"][0] == terminal[0]["id"]  # best-ranked first
    assert terminal[0]["first_at"] < terminal[0]["last_at"] and terminal[0]["duration_s"] == 50
    # `limit` applies to moments, not frames
    assert len(services.queries.search("plugins", None, None, None, 2)["hits"]) == 2
    # different snippet text within the window is a different moment
    add(services, t - 1700, "terminal", "Terminal", "otro error distinto con plugins")
    assert services.queries.search("plugins", None, None, None, 10)["moments_total"] == 4


def test_group_moments_orders_by_best_rank_and_time_window():
    def cand(i, at, snippet="same [text]"):
        return Candidate(i, at, "app", "win", "", snippet)

    ranked = [(cand(1, 0), -1.0), (cand(2, 300), -3.0), (cand(3, 1200), -2.0), (cand(4, 1300, "other"), -0.5)]
    moments = group_moments(ranked, 600)
    assert [m["frame_ids"] for m in moments] == [[2, 1], [3], [4]]
    assert moments[0]["count"] == 2 and moments[0]["first_at"] == 0 and moments[0]["last_at"] == 300


def test_query_terms_and_tokens_fold_like_fts():
    assert tokens("Línea de TIEMPO, auto-save!") == ["linea", "de", "tiempo", "auto", "save"]
    assert query_terms("error que vi") == [("error", False), ("que", False), ("vi", False)]
    assert query_terms("presupue")[-1] == ("presupue", True)
