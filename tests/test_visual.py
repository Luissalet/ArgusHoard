"""Visual search: indexing (resumable, throttled, deletion-aware), cosine search, fusion with OCR, modes, similar frames, the API and the
agent tools. Everything but the last test runs on the deterministic colour embedder (`ARGUS_VISUAL=fake`): no model, no download."""

from __future__ import annotations

import http.server
import json
import os
import struct
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from argus import visual_model
from argus.hoard_link.docs.imaging import dhash
from argus.services import Services
from argus.store import Block
from argus.visual import VisualService, VisualUnavailable, fuse_hits
from conftest import make_config

BLUE, RED, GREEN, DARK, WHITE = (10, 20, 220), (220, 20, 20), (20, 200, 30), (25, 25, 28), (245, 245, 245)


def svc_for(tmp_path, **overrides) -> Services:
    return Services(make_config(tmp_path, visual_backend=overrides.pop("visual_backend", "fake"), **overrides))


def add(svc, at, app, title, colour, text="", interval=5) -> int:
    image = Image.new("RGB", (640, 360), colour)
    fid = svc.frames.insert_frame(image, captured_at=at, interval_s=interval, monitor=1, app=app, window_title=title, phash=dhash(image))
    svc.frames.set_ocr_result(fid, [Block(text, 0, 0, 10, 10)] if text else [], text, 1, "stub")
    return fid


def base() -> float:
    return time.time() - 7200


def vec_count(svc) -> int:
    with svc.db.lock:
        return int(svc.db.conn.execute("SELECT COUNT(*) AS n FROM frame_vectors").fetchone()["n"])


def index_all(visual) -> int:
    done = 0
    while True:
        n = visual.index_batch(3)
        if not n:
            return done
        done += n


@pytest.fixture
def svc(tmp_path):
    service = svc_for(tmp_path)
    yield service
    service.stop()


@pytest.fixture
def gallery(svc):
    """Five frames of different looks, far enough apart to be separate moments; the invoice has OCR text."""
    t = base()
    ids = {
        "blue": add(svc, t, "chrome", "Ventas - grafica", BLUE, "ventas trimestrales"),
        "red": add(svc, t + 1000, "chrome", "Reparto - tarta", RED, "reparto por zonas"),
        "green": add(svc, t + 2000, "excel", "Hoja de calculo", GREEN, "total de la columna"),
        "dark": add(svc, t + 3000, "code", "main.py - Editor", DARK, "def main(): return 0"),
        "invoice": add(svc, t + 4000, "acrobat", "Factura Iberdrola", WHITE, "Factura de Iberdrola importe 83,20 euros"),
    }
    assert index_all(svc.visual) == 5
    return ids


# ------------------------------------------------------------------------------------------------------------ the embedders
def test_fake_embedder_is_deterministic_and_understands_colours():
    e = visual_model.FakeEmbedder()
    blue = Image.new("RGB", (64, 36), BLUE)
    a, b = e.embed_images([blue])[0], e.embed_images([blue])[0]
    assert np.allclose(a, b) and abs(float(np.linalg.norm(a)) - 1.0) < 1e-5
    assert float(e.embed_text("la gráfica azul".replace("gráfica", "grafica")) @ a) > 0.7 > float(e.embed_text("rojo") @ a)
    assert float(e.embed_text("oscuro") @ e.embed_images([Image.new("RGB", (64, 36), DARK)])[0]) > 0.9


def test_wordpiece_tokenizer_matches_bert_rules():
    vocab = {t: i for i, t in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "gr", "##áfica", "azul", "factura", "de", ",", "日", "本", "##ura"])}
    tok = visual_model.WordPiece(vocab)
    assert tok.encode("gráfica azul") == [2, 4, 5, 6, 3]  # cased, accents kept, greedy longest match with ## pieces
    assert tok.encode("factura de, azul") == [2, 7, 8, 9, 6, 3]  # punctuation is its own token
    assert tok.encode("日本") == [2, 10, 11, 3]  # CJK characters stand alone
    assert tok.encode("zzz") == [2, 1, 3]  # unknown word
    assert tok.encode("azul " * 300)[-1] == 3 and len(tok.encode("azul " * 300)) == visual_model.TEXT_MAX_TOKENS


def test_safetensors_reader(tmp_path):
    weights = np.arange(6, dtype="<f4").reshape(2, 3)
    header = json.dumps({"linear.weight": {"dtype": "F32", "shape": [2, 3], "data_offsets": [0, 24]}}).encode()
    path = tmp_path / "w.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + weights.tobytes())
    assert np.array_equal(visual_model.read_safetensors(path)["linear.weight"], weights)


def test_preprocess_letterboxes_the_whole_screen_into_224():
    out = visual_model.preprocess(Image.new("RGB", (1280, 720), (255, 255, 255)))
    assert out.shape == (3, 224, 224) and out.dtype == np.float32
    white, grey = out[0, 112, 112], out[0, 2, 112]  # the screen in the middle, neutral bars above and below (nothing cropped)
    assert white > 1.5 and abs(grey) < 0.8 and out[0, 221, 112] == pytest.approx(grey)
    tall = visual_model.preprocess(Image.new("RGB", (300, 900), (0, 0, 0)))
    assert tall.shape == (3, 224, 224) and tall[0, 112, 112] < -1.5 and abs(tall[0, 112, 2]) < 0.8


def test_download_writes_files_then_manifest_and_a_404_leaves_nothing(tmp_path, monkeypatch):
    payloads = {f"/{f.local}": (f.local.encode() * 50) for f in visual_model.FILES}
    payloads["/vision-v2.onnx"] = b"v2" * 50
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body = payloads.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        good = tuple(visual_model.ModelFile(f.local, f"http://127.0.0.1:{port}/{f.local}", 0) for f in visual_model.FILES)
        monkeypatch.setattr(visual_model, "FILES", good)
        target = tmp_path / "models"
        seen = []
        visual_model.download_model(target, lambda name, done, total: seen.append((name, done, total)))
        assert visual_model.model_present(target) and seen and all(done <= total for _, done, total in seen)
        assert not list(target.glob("*.part"))
        fetched = len(requests)
        visual_model.download_model(target)  # everything is there already: nothing is fetched again
        assert len(requests) == fetched
        moved = (visual_model.ModelFile("vision.onnx", f"http://127.0.0.1:{port}/vision-v2.onnx", 0),) + good[1:]
        monkeypatch.setattr(visual_model, "FILES", moved)  # a changed model URL replaces the old file
        visual_model.download_model(target)
        assert requests[fetched:] == ["/vision-v2.onnx"] and (target / "vision.onnx").read_bytes() == b"v2" * 50
        monkeypatch.setattr(visual_model, "FILES", good)

        bad = good[:2] + (visual_model.ModelFile("vocab.txt", f"http://127.0.0.1:{port}/missing", 0),) + good[3:]
        monkeypatch.setattr(visual_model, "FILES", bad)
        broken = tmp_path / "broken"
        with pytest.raises(visual_model.DownloadError):
            visual_model.download_model(broken)
        assert not visual_model.model_present(broken) and not list(broken.glob("*.part")) and not (broken / visual_model.MANIFEST).exists()
    finally:
        server.shutdown()


# ------------------------------------------------------------------------------------------------------------ indexing
def test_indexing_is_resumable_newest_first_and_never_repeats_work(tmp_path):
    first = svc_for(tmp_path)
    t = base()
    ids = [add(first, t + i * 700, "app", f"ventana {i}", BLUE) for i in range(7)]
    assert first.visual.index_batch(3) == 3
    with first.db.lock:
        done = {r["frame_id"] for r in first.db.conn.execute("SELECT frame_id FROM frame_vectors")}
    assert done == set(ids[-3:])  # the newest frames first
    first.stop()

    # a new process over the same data: it only embeds what is missing
    second = svc_for(tmp_path)
    counter = visual_model.FakeEmbedder()
    second.visual._embedder = counter
    assert index_all(second.visual) == 4 and counter.images_embedded == 4
    assert vec_count(second) == 7 and second.visual.counts() == {"total": 7, "indexed": 7, "stale": 0}
    assert second.visual.index_batch() == 0
    second.stop()


def test_only_frames_argus_stores_are_embedded(svc):
    t = base()
    add(svc, t, "a", "w", BLUE)
    svc.frames.extend_frame(1, t + 99)  # a repeated screen only extends the stored frame: nothing new to embed
    assert svc.visual.counts()["total"] == 1 and index_all(svc.visual) == 1


def test_a_frame_with_a_missing_image_is_skipped_not_retried(svc):
    t = base()
    bad = add(svc, t, "a", "w", BLUE)
    good = add(svc, t + 10, "a", "w2", RED)
    info = svc.frames.image_file(bad)
    info[0].unlink()
    assert index_all(svc.visual) == 1  # the unreadable one is neither stored nor retried forever
    assert svc.visual.failed == {bad} and vec_count(svc) == 1
    assert svc.visual.status()["failed"] == 1 and svc.visual.vector_of(good, svc.visual.model_id()) is not None


def test_background_thread_indexes_and_yields_to_ocr(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_VISUAL_DUTY", "1.0")
    svc = svc_for(tmp_path)
    busy = [1]
    svc.visual.busy = lambda: busy[0]
    t = base()
    for i in range(6):
        add(svc, t + i * 700, "app", f"w{i}", BLUE)
    svc.visual.start()
    try:
        time.sleep(1.5)
        assert vec_count(svc) == 0  # the OCR queue has work: the indexer stands aside
        busy[0] = 0
        deadline = time.time() + 15
        while time.time() < deadline and vec_count(svc) < 6:
            time.sleep(0.1)
        assert vec_count(svc) == 6
        status = svc.visual.status()
        assert status["indexed"] == 6 and status["pending"] == 0 and status["device"] == "cpu"
    finally:
        svc.stop()


def test_setting_off_stops_indexing_and_search_falls_back_to_text(svc, gallery):
    assert svc.visual.status()["active"] is True
    svc.update_settings({"visual_search": False})
    assert svc.visual.usable() is False and svc.visual.index_batch() == 0
    result = svc.search("azul", None, None, None, 10, "both")
    assert result["mode"] == "text" and result["visual"]["used"] is False
    with pytest.raises(VisualUnavailable):
        svc.search("azul", None, None, None, 10, "visual")
    svc.update_settings({"visual_search": True})
    assert svc.search("azul", None, None, None, 10, "visual")["hits"]


def test_missing_model_means_not_available_and_text_search_still_works(tmp_path):
    svc = svc_for(tmp_path, visual_backend="auto")  # no model files in this data dir
    try:
        add(svc, base(), "a", "Factura Iberdrola", WHITE, "factura de iberdrola")
        status = svc.visual.status()
        assert status["available"] is False and status["active"] is False and status["download"]["state"] == "idle"
        found = svc.search("iberdrola", None, None, None, 10, "both")
        assert found["mode"] == "text" and len(found["hits"]) == 1 and found["visual"]["reason"]
        with pytest.raises(VisualUnavailable):
            svc.search("azul", None, None, None, 10, "visual")
    finally:
        svc.stop()


def test_changing_the_model_replaces_vectors_and_never_mixes_spaces(svc, gallery):
    old = svc.visual.model_id()

    class Other(visual_model.FakeEmbedder):
        model_id = "fake-other-v2"

    svc.visual._embedder = Other()
    assert svc.visual.counts() == {"total": 5, "indexed": 0, "stale": 5}
    assert svc.search("azul", None, None, None, 10, "both")["mode"] == "text"  # no vector of the new model yet
    assert index_all(svc.visual) == 5
    assert svc.visual.counts() == {"total": 5, "indexed": 5, "stale": 0} and vec_count(svc) == 5  # replaced, not duplicated
    assert old != svc.visual.model_id()
    assert svc.search("azul", None, None, None, 10, "visual")["hits"][0]["id"] == gallery["blue"]


# ------------------------------------------------------------------------------------------------------------ deletion
def test_deleting_a_frame_deletes_its_vector_and_it_leaves_the_results(svc, gallery):
    first = svc.search("azul", None, None, None, 10, "visual")  # loads the in-memory matrix
    assert first["hits"][0]["id"] == gallery["blue"]
    assert svc.frames.delete_frames([gallery["blue"]]) == 1
    assert vec_count(svc) == 4
    with svc.db.lock:
        assert svc.db.conn.execute("SELECT 1 FROM frame_vectors WHERE frame_id = ?", (gallery["blue"],)).fetchone() is None
    after = svc.search("azul", None, None, None, 10, "visual")
    assert gallery["blue"] not in {i for h in after["hits"] for i in h["frame_ids"]}
    # a vector written for a frame that no longer exists is refused instead of dangling
    svc.visual.put_vectors([gallery["blue"]], np.ones((1, visual_model.FakeEmbedder.dim), dtype=np.float32), svc.visual.model_id())
    assert vec_count(svc) == 4


def test_range_deletion_and_retention_remove_vectors_too(svc):
    t = time.time()
    add(svc, t - 40 * 86400, "a", "viejo", BLUE)
    recent = add(svc, t - 600, "a", "reciente", RED)
    add(svc, t - 3000, "a", "medio", GREEN)
    assert index_all(svc.visual) == 3
    svc.search("rojo", None, None, None, 5, "visual")  # warm the cache
    svc.settings.update({"retention_days": 30})
    assert svc.janitor.run()["deleted_by_age"] == 1 and vec_count(svc) == 2
    assert svc.janitor.delete_range(t - 3600, t - 2400) == 1 and vec_count(svc) == 1
    remaining = svc.search("rojo", None, None, None, 5, "visual")["hits"]
    assert [h["id"] for h in remaining] == [recent]


def test_reindex_forgets_every_vector_and_the_indexer_starts_again(svc, gallery):
    assert svc.visual.reindex() == 5 and vec_count(svc) == 0
    assert svc.search("azul", None, None, None, 5, "both")["mode"] == "text"
    assert index_all(svc.visual) == 5


# ------------------------------------------------------------------------------------------------------------ search and fusion
def test_visual_mode_ranks_by_look(svc, gallery):
    for query, expected in (("azul", "blue"), ("blue", "blue"), ("rojo", "red"), ("verde", "green"), ("fondo oscuro", "dark"), ("white", "invoice")):
        hits = svc.search(query, None, None, None, 5, "visual")["hits"]
        assert hits[0]["id"] == gallery[expected], (query, hits[0]["window_title"])
        assert hits[0]["via"] == ["visual"] and hits[0]["visual_score"] > hits[1]["visual_score"]


def test_text_mode_ignores_the_image_index(svc, gallery):
    result = svc.search("iberdrola", None, None, None, 10, "text")
    assert [h["id"] for h in result["hits"]] == [gallery["invoice"]] and result["mode"] == "text"
    assert svc.search("azul", None, None, None, 10, "text")["hits"] == []  # nobody wrote "azul": a text search finds nothing


def test_both_finds_text_and_looks_and_ranks_items_found_by_both_first(svc, gallery):
    ocr = svc.search("factura iberdrola", None, None, None, 10, "both")
    assert ocr["mode"] == "both" and ocr["hits"][0]["id"] == gallery["invoice"] and ocr["hits"][0]["via"] == ["text"]
    assert all(h["id"] == gallery["invoice"] for h in ocr["hits"])  # no visual noise next to a real OCR hit
    visual = svc.search("la pantalla azul", None, None, None, 10, "both")
    assert visual["hits"][0]["id"] == gallery["blue"] and visual["hits"][0]["via"] == ["visual"]
    mixed = svc.search("ventas azul", None, None, None, 10, "both")  # no frame has both words in its text, but one looks blue
    assert mixed["hits"][0]["id"] == gallery["blue"] and mixed["hits"][0]["via"] == ["visual"]
    # the same frame is found by both sides when the words and the look agree
    with svc.db.lock:
        svc.db.conn.execute("UPDATE frames_fts SET text = text || ' azul' WHERE rowid = ?", (gallery["blue"],))
    merged = svc.search("azul", None, None, None, 10, "both")["hits"][0]
    assert merged["id"] == gallery["blue"] and set(merged["via"]) == {"text", "visual"} and merged["visual_score"] > 0.5
    assert merged["score"] > 1 / 61 and merged["rank"] < 0


def test_both_without_any_vector_is_the_old_text_search(svc):
    add(svc, base(), "a", "Factura", WHITE, "factura de agua")
    result = svc.search("factura", None, None, None, 10, "both")
    assert result["mode"] == "text" and result["visual"]["used"] is False and result["visual"]["indexing"] is True
    assert len(result["hits"]) == 1


def test_filters_apply_to_visual_search(svc, gallery):
    only_code = svc.search("azul", None, None, "code", 10, "visual")["hits"]
    assert [h["id"] for h in only_code] == [gallery["dark"]]
    t = base()
    window = svc.search("azul", t + 500, t + 1500, None, 10, "visual")["hits"]
    assert [h["id"] for h in window] == [gallery["red"]]


def test_consecutive_similar_frames_fold_into_one_moment(svc):
    t = base()
    run = [add(svc, t + i * 5, "chrome", "Ventas", BLUE) for i in range(6)]
    other = add(svc, t + 5000, "chrome", "Otra", BLUE)
    index_all(svc.visual)
    hits = svc.search("azul", None, None, None, 10, "visual")["hits"]
    assert {h["count"] for h in hits} == {6, 1}
    folded = next(h for h in hits if h["count"] == 6)
    assert sorted(folded["frame_ids"]) == sorted(run) and folded["first_at"] < folded["last_at"]
    assert next(h for h in hits if h["count"] == 1)["id"] == other


def test_fusion_floor_drops_scores_that_are_not_clearly_above_the_rest_of_the_index(svc, monkeypatch):
    t = base()
    a, b, c = (add(svc, t + i * 2000, "app", f"w{i}", BLUE) for i in range(3))
    index_all(svc.visual)
    scored = [(a, 0.30), (b, 0.29), (c, 0.27)]
    stats = {"n": 500, "mean": 0.22, "std": 0.03}  # an index of 500 frames: a match must sit 2 sigma above the mean (0.28)
    monkeypatch.setattr(VisualService, "_score", staticmethod(lambda *args: (list(scored), dict(stats))))
    hits, info = svc.visual.visual_moments("azul", None, None, None, relevant_only=True)
    assert [h["id"] for h in hits] == [a, b] and info["best_score"] == 0.3
    everything, _ = svc.visual.visual_moments("azul", None, None, None, relevant_only=False)  # explicit visual mode never filters
    assert len(everything) == 3
    stats["n"] = 10  # too small an index to know what unrelated looks like: only the absolute and relative floors apply
    small, _ = svc.visual.visual_moments("azul", None, None, None, relevant_only=True)
    assert [h["id"] for h in small] == [a, b, c]


def test_fuse_hits_is_reciprocal_rank_fusion():
    def hit(i, frames, **extra):
        return {"id": i, "frame_ids": frames, "count": len(frames), "snippet": "", **extra}

    text = [hit(1, [1]), hit(2, [2]), hit(3, [3])]
    visual = [hit(9, [9], visual_score=0.4), hit(3, [3, 33], visual_score=0.3), hit(8, [8], visual_score=0.2)]
    fused = fuse_hits(text, visual, 10)
    ids = [h["id"] for h in fused]
    assert ids[0] == 3  # in both lists
    assert set(ids) == {1, 2, 3, 9, 8}
    top = fused[0]
    assert top["via"] == ["text", "visual"] and top["visual_score"] == 0.3 and top["frame_ids"] == [3, 33] and top["count"] == 2
    assert top["score"] == pytest.approx(1 / 63 + 1 / 62, abs=1e-5)
    assert [h["via"] for h in fused if h["id"] in (1, 2)] == [["text"], ["text"]]
    assert fuse_hits([], visual, 2)[0]["id"] == 9 and fuse_hits(text, [], 2)[1]["id"] == 2 and len(fuse_hits(text, visual, 2)) == 2


# ------------------------------------------------------------------------------------------------------------ similar frames
def test_similar_frames_exclude_the_frames_own_moment(svc):
    t = base()
    mine = [add(svc, t + i * 5, "chrome", "Ventas", BLUE) for i in range(3)]
    far = add(svc, t + 5000, "excel", "Otra hoja", BLUE)
    red = add(svc, t + 6000, "chrome", "Tarta", RED)
    index_all(svc.visual)
    result = svc.visual.similar(mine[0], 10)
    assert [h["id"] for h in result["hits"]][0] == far and result["mode"] == "similar"
    assert not set(mine) & {i for h in result["hits"] for i in h["frame_ids"]}
    assert result["hits"][0]["visual_score"] > result["hits"][-1]["visual_score"] and red in {h["id"] for h in result["hits"]}
    same = svc.visual.similar(mine[0], 10, same_moment=True)
    assert set(mine[1:]) <= {i for h in same["hits"] for i in h["frame_ids"]}


def test_similar_embeds_a_frame_that_is_not_indexed_yet(svc):
    t = base()
    a = add(svc, t, "x", "a", BLUE)
    b = add(svc, t + 3000, "y", "b", BLUE)
    assert vec_count(svc) == 0
    result = svc.visual.similar(a, 5)
    assert [h["id"] for h in result["hits"]] == []  # b is not indexed, only a (just embedded)
    svc.visual.index_batch(5)
    assert [h["id"] for h in svc.visual.similar(a, 5)["hits"]] == [b]
    with pytest.raises(LookupError):
        svc.visual.similar(99999, 5)


# ------------------------------------------------------------------------------------------------------------ API and agent tools
@pytest.fixture
def vclient(tmp_path):
    from fastapi.testclient import TestClient

    from argus.main import create_app

    app = create_app(make_config(tmp_path, visual_backend="fake"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.services = app.state.services
        yield client


def wait_indexed(svc, count, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if vec_count(svc) >= count:
            return
        time.sleep(0.1)
    raise AssertionError(f"only {vec_count(svc)} of {count} frames indexed")


def test_api_search_modes_similar_status_and_errors(vclient):
    svc = vclient.services
    t = base()
    blue = add(svc, t, "chrome", "Ventas", BLUE, "ventas")
    red = add(svc, t + 2000, "chrome", "Tarta", RED, "reparto")
    wait_indexed(svc, 2)
    r = vclient.get("/api/search", params={"q": "azul", "mode": "visual"})
    assert r.status_code == 200 and r.json()["hits"][0]["id"] == blue and r.json()["hits"][0]["via"] == ["visual"]
    both = vclient.get("/api/search", params={"q": "reparto"}).json()  # default mode is both
    assert both["mode"] == "both" and both["hits"][0]["id"] == red
    assert vclient.get("/api/search", params={"q": "azul", "mode": "text"}).json()["hits"] == []
    assert vclient.get("/api/search", params={"q": "azul", "mode": "nope"}).status_code == 400
    sim = vclient.get(f"/api/frames/{blue}/similar").json()
    assert sim["mode"] == "similar" and [h["id"] for h in sim["hits"]] == [red]
    assert vclient.get("/api/frames/424242/similar").status_code == 404
    status = vclient.get("/api/visual").json()
    assert status["indexed"] == 2 and status["total"] == 2 and status["active"] and status["device"] == "cpu"
    assert vclient.get("/api/status").json()["visual"]["indexed"] == 2
    assert vclient.put("/api/settings", json={"visual_search": False}).json()["visual_search"] is False
    assert vclient.get("/api/search", params={"q": "azul", "mode": "visual"}).status_code == 409
    assert vclient.get("/api/search", params={"q": "reparto"}).json()["mode"] == "text"
    assert vclient.get(f"/api/frames/{blue}/similar").status_code == 409
    assert vclient.post("/api/visual/download").json()["state"] == "error"  # the fake backend has nothing to download
    vclient.put("/api/settings", json={"visual_search": True})
    assert vclient.post("/api/visual/reindex").json()["removed"] == 2
    wait_indexed(svc, 2)


def test_agent_tools_search_by_look_and_status(vclient):
    svc = vclient.services
    t = base()
    blue = add(svc, t, "chrome", "Ventas", BLUE)
    add(svc, t + 2000, "chrome", "Tarta", RED)
    wait_indexed(svc, 2)
    auth = {"Authorization": f"Bearer {svc.token}"}

    def call(name, arguments=None):
        return vclient.post("/api/agent/call", json={"name": name, "arguments": arguments or {}}, headers=auth)

    found = call("screen_search", {"q": "pantalla azul", "mode": "visual"}).json()
    assert found["hits"][0]["id"] == blue and found["hits"][0]["via"] == ["visual"] and found["visual"]["used"] is True
    default = call("screen_search", {"q": "pantalla azul"}).json()
    assert default["mode"] == "both" and default["hits"][0]["id"] == blue
    assert call("screen_search", {"q": "x", "mode": "bogus"}).status_code == 400
    status = call("screen_status").json()
    assert status["visual"]["indexed"] == 2 and status["visual"]["active"] is True
    similar = call("screen_similar", {"id": blue}).json()
    assert similar["frame_id"] == blue and isinstance(similar["hits"], list)
    svc.update_settings({"visual_search": False})
    assert call("screen_search", {"q": "azul", "mode": "visual"}).status_code == 409
    assert call("screen_similar", {"id": blue}).status_code == 409
    assert call("screen_search", {"q": "azul"}).json()["visual"]["used"] is False


# ------------------------------------------------------------------------------------------------------------ the real model (optional)
def real_model_dir() -> Path | None:
    candidates = [os.environ.get("ARGUS_TEST_MODEL_DATA"), str(Path(__file__).resolve().parent.parent / "data")]
    for data in candidates:
        if data and visual_model.model_present(visual_model.model_dir(Path(data))):
            return visual_model.model_dir(Path(data))
    return None


def chart(kind: str) -> Image.Image:
    image = Image.new("RGB", (1280, 720), (250, 250, 250))
    d = ImageDraw.Draw(image)
    if kind == "bars":
        for i, h in enumerate((200, 330, 260, 440, 380)):
            d.rectangle([160 + i * 190, 620 - h, 280 + i * 190, 620], fill=(20, 80, 220))
        d.line([120, 620, 1160, 620], fill=(0, 0, 0), width=4)
    elif kind == "pie":
        d.pieslice([340, 100, 940, 700], 0, 140, fill=(220, 30, 30))
        d.pieslice([340, 100, 940, 700], 140, 250, fill=(240, 150, 150))
        d.pieslice([340, 100, 940, 700], 250, 360, fill=(120, 20, 20))
    else:
        image = Image.new("RGB", (1280, 720), (30, 30, 36))
        d = ImageDraw.Draw(image)
        for i in range(20):
            d.rectangle([60 + (i % 3) * 30, 40 + i * 32, 400 + (i * 97) % 600, 56 + i * 32], fill=(90, 200, 120))
    return image


@pytest.mark.slow
@pytest.mark.skipif(real_model_dir() is None, reason="the real visual model is not downloaded (ARGUS_TEST_MODEL_DATA or data/models)")
def test_real_clip_model_matches_descriptions_on_cpu():
    embedder = visual_model.ClipOnnxEmbedder(real_model_dir(), threads=1)
    assert embedder.device == "cpu" and os.environ["CUDA_VISIBLE_DEVICES"] == "-1"
    vectors = embedder.embed_images([chart("bars"), chart("pie"), chart("code")])
    assert vectors.shape == (3, 512) and np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)
    for query, expected in (("gráfica de barras azul", 0), ("blue bar chart", 0), ("gráfico circular rojo", 1), ("código en fondo oscuro", 2)):
        scores = vectors @ embedder.embed_text(query)
        assert int(np.argmax(scores)) == expected, (query, scores)
