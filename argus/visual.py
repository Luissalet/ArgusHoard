"""Visual search: embeddings of the stored frames, the background indexer, cosine search and its fusion with the OCR search.

* **Index.** One 512-d vector per stored frame (`frame_vectors`, float16 BLOB, ~1 KB), made by `visual_model` on the CPU from the frame's
  stored WebP. Only frames Argus keeps are embedded; deleting a frame deletes its vector in the same transaction
  (`FrameStore.delete_frames`). A vector carries the id of the model that made it: when the model changes, the old ones are replaced
  as the indexer reaches them and never mixed into a search.
* **Indexer.** One daemon thread, lowest priority, batches of 4, sleeps as long as it computed (about half of one core at most),
  stands aside while the OCR queue has work, newest frames first, resumable (it asks the database what is missing), idle when the
  setting is off or the model is not there.
* **Search.** The query is embedded by the text tower and compared with every vector by cosine (brute force over a float16 matrix
  held in memory, exact and fast to ~100k frames). Visual hits are folded into *moments* like the OCR ones and fused with them by
  reciprocal rank (`hoard_link.docs.vecmath.rrf`), so "factura de Iberdrola" still finds its text and "gráfica azul" finds the chart.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

import numpy as np
from PIL import Image

from . import visual_model
from .config import Config
from .db import Database
from .hoard_link.docs import vecmath
from .queries import Queries, _excerpt, _frame_row
from .search import Candidate, group_moments
from .settings import SettingsStore
from .store import FrameStore
from .timeparse import iso_local

log = logging.getLogger("argus.visual")

MODES = ("text", "visual", "both")
BATCH = 4
IDLE_POLL_S = 5.0
RETRY_LOAD_S = 60.0
IDLE_UNLOAD_S = 600.0  # the model holds about 500 MB of RAM: let go of it after ten idle minutes (it reloads in a second when needed)
CANDIDATES = 300  # best frames taken from the matrix before they are folded into moments
RRF_K = 60
# A visual hit must look like the query to count in a fusion. Without a floor the nearest frames always come back, however unrelated,
# and would tie with a real OCR hit at rank 1. CLIP cosines are compressed (about 0.20-0.24 for unrelated screens, 0.25-0.32 for a match),
# so the floor is: at least MIN_ABS, within REL of the best frame, and, once the index is big enough to say what "unrelated" scores
# (Z_MIN_FRAMES), at least Z standard deviations above the mean score of the whole index.
MIN_ABS = 0.20
REL = 0.05
Z = 2.0
Z_MIN_FRAMES = 50
MAX_FAILED = 1000


class VisualUnavailable(RuntimeError):
    """Visual search was asked for explicitly and cannot run (disabled, model missing or not loadable)."""


def _lower_thread_priority() -> None:
    """Below-normal for the calling thread (the indexer): capture and OCR keep their share of the CPU."""
    try:
        if os.name == "nt":
            import ctypes

            kernel = ctypes.windll.kernel32
            kernel.SetThreadPriority(kernel.GetCurrentThread(), -2)  # THREAD_PRIORITY_LOWEST
        else:
            os.nice(10)
    except Exception:  # pragma: no cover - cosmetic
        pass


def fuse_hits(text_hits: list[dict], visual_hits: list[dict], limit: int, k: int = RRF_K, weights: tuple[float, float] = (1.0, 1.0)) -> list[dict]:
    """Reciprocal-rank fusion of two lists of moments. A visual moment that shares a frame with an OCR moment is the same item (it
    keeps the OCR snippet and gains the visual score); the rest stand alone. Items found by both sides rank first, as RRF dictates."""
    items: list[dict] = []
    owner: dict[int, int] = {}
    for hit in text_hits:
        item = {**hit, "frame_ids": list(hit["frame_ids"]), "via": ["text"], "visual_score": None}
        items.append(item)
        for fid in item["frame_ids"]:
            owner.setdefault(fid, len(items) - 1)
    text_order = list(range(len(items)))
    visual_order: list[int] = []
    for hit in visual_hits:
        target = next((owner[fid] for fid in hit["frame_ids"] if fid in owner), None)
        if target is None:
            items.append({**hit, "frame_ids": list(hit["frame_ids"]), "via": ["visual"]})
            target = len(items) - 1
            for fid in hit["frame_ids"]:
                owner.setdefault(fid, target)
        else:
            item = items[target]
            if "visual" not in item["via"]:
                item["via"].append("visual")
            item["visual_score"] = max(item["visual_score"] or 0.0, hit["visual_score"])
            for fid in hit["frame_ids"]:
                if fid not in item["frame_ids"]:
                    item["frame_ids"].append(fid)
                owner.setdefault(fid, target)
            item["count"] = len(item["frame_ids"])
        if target not in visual_order:
            visual_order.append(target)
    fused = vecmath.rrf([text_order, visual_order], weights=list(weights), k=k)
    out = []
    for index, score in fused[:limit]:
        item = items[index]
        item["score"] = round(score, 5)
        item["rank"] = round(-score, 5)  # same convention as the OCR rank: negative, lower is better
        out.append(item)
    return out


class VisualService:
    def __init__(self, config: Config, db: Database, frames: FrameStore, queries: Queries, settings: SettingsStore,
                 busy: Callable[[], int] | None = None, embedder_factory: Callable[[], object | None] | None = None):
        self.config = config
        self.db = db
        self.frames = frames
        self.queries = queries
        self.settings = settings
        self.busy = busy or (lambda: 0)  # work waiting in the OCR queue: the indexer yields while it is non-zero
        self.directory = visual_model.model_dir(config.data_dir)
        self._factory = embedder_factory or (lambda: visual_model.load_embedder(config.visual_backend, config.data_dir))
        self._embedder = None
        self._engine_lock = threading.Lock()
        self._load_failed_at = 0.0
        self._last_used = time.monotonic()
        self.engine_error: str | None = None
        # matrix cache (lock order: _cache_lock, then db.lock; the delete hook only touches _pending_lock)
        self._cache_lock = threading.Lock()
        self._ids = np.zeros(0, dtype=np.int64)
        self._mat = np.zeros((0, 0), dtype=np.float16)
        self._n = 0
        self._cache_model: str | None = None
        self._pending_lock = threading.Lock()
        self._pending_deletes: set[int] = set()
        frames.delete_hooks.append(self._on_deleted)
        # indexer
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.failed: set[int] = set()
        self.indexed_session = 0
        self.avg_ms: float | None = None
        self.last_error: str | None = None
        self.working = False
        self.duty = min(1.0, max(0.05, float(os.environ.get("ARGUS_VISUAL_DUTY", "0.5") or 0.5)))
        # download
        self._download_lock = threading.Lock()
        self.download: dict = {"state": "idle", "file": None, "done": 0, "total": 0, "error": None}

    # ------------------------------------------------------------------ model availability
    def kind(self) -> str:
        return (self.config.visual_backend or "auto").lower()

    def model_ready(self) -> bool:
        """The model can be loaded: its files are on disk (or the fake/none backend decides)."""
        kind = self.kind()
        if kind == "none":
            return False
        if kind == "fake":
            return True
        return visual_model.model_present(self.directory)

    def enabled(self) -> bool:
        return bool(self.settings.get().visual_search)

    def usable(self) -> bool:
        return self.enabled() and self.model_ready()

    def engine(self):
        """The loaded embedder, or None (disabled, model missing, or it failed to load: see `engine_error`)."""
        if not self.usable():
            return None
        with self._engine_lock:
            self._last_used = time.monotonic()
            if self._embedder is None:
                if self.engine_error and time.monotonic() - self._load_failed_at < RETRY_LOAD_S:
                    return None
                try:
                    self._embedder = self._factory()
                    self.engine_error = None
                except Exception as error:  # a damaged file, no onnxruntime
                    self.engine_error = f"{type(error).__name__}: {error}"[:300]
                    self._load_failed_at = time.monotonic()
                    log.warning("visual model failed to load: %s", self.engine_error)
                    return None
            return self._embedder

    def model_id(self) -> str:
        if self._embedder is not None:
            return self._embedder.model_id
        return "fake-colour-v1" if self.kind() == "fake" else visual_model.MODEL_ID

    def unload(self) -> None:
        with self._engine_lock:
            self._embedder = None
        self._drop_cache()

    # ------------------------------------------------------------------ vectors in the database
    def _on_deleted(self, ids: list[int]) -> None:
        with self._pending_lock:
            self._pending_deletes.update(ids)

    def _apply_deletes(self) -> None:  # _cache_lock held
        with self._pending_lock:
            gone, self._pending_deletes = self._pending_deletes, set()
        if gone and self._n:
            keep = ~np.isin(self._ids[: self._n], np.fromiter(gone, dtype=np.int64, count=len(gone)))
            if not keep.all():
                self._ids = self._ids[: self._n][keep].copy()
                self._mat = self._mat[: self._n][keep].copy()
                self._n = len(self._ids)

    def _drop_cache(self) -> None:
        with self._cache_lock:
            self._ids = np.zeros(0, dtype=np.int64)
            self._mat = np.zeros((0, 0), dtype=np.float16)
            self._n = 0
            self._cache_model = None

    def put_vectors(self, ids: list[int], vectors: np.ndarray, model: str) -> None:
        rows = [(fid, model, int(vectors.shape[1]), np.asarray(v, dtype="<f2").tobytes(), time.time(), fid) for fid, v in zip(ids, vectors)]
        with self.db.lock:  # a frame deleted since it was read has no row to hang a vector on: the WHERE EXISTS skips it
            self.db.conn.executemany(
                "INSERT INTO frame_vectors(frame_id, model, dim, vec, created_at) SELECT ?, ?, ?, ?, ? "
                "WHERE EXISTS (SELECT 1 FROM frames WHERE id = ?) "
                "ON CONFLICT(frame_id) DO UPDATE SET model = excluded.model, dim = excluded.dim, vec = excluded.vec, created_at = excluded.created_at",
                rows,
            )
        with self._cache_lock:
            if self._cache_model == model:
                self._apply_deletes()
                self._append(list(ids), np.asarray(vectors).astype(np.float16))

    def _append(self, ids: list[int], vectors: np.ndarray) -> None:  # _cache_lock held
        new_ids = np.asarray(ids, dtype=np.int64)
        dim = vectors.shape[1]
        if self._mat.shape[1] != dim:  # first rows, or an embedder with another width: start the buffers again
            self._ids, self._mat, self._n = np.zeros(0, dtype=np.int64), np.zeros((0, dim), dtype=np.float16), 0
        if self._n:
            keep = ~np.isin(self._ids[: self._n], new_ids)  # a re-embedded frame replaces its old row
            if not keep.all():
                self._ids = self._ids[: self._n][keep].copy()
                self._mat = self._mat[: self._n][keep].copy()
                self._n = len(self._ids)
        need = self._n + len(new_ids)
        if need > len(self._ids):
            capacity = max(need, int(len(self._ids) * 1.5), 256)
            ids_buf = np.zeros(capacity, dtype=np.int64)
            mat_buf = np.zeros((capacity, dim), dtype=np.float16)
            ids_buf[: self._n] = self._ids[: self._n]
            mat_buf[: self._n] = self._mat[: self._n]
            self._ids, self._mat = ids_buf, mat_buf
        self._ids[self._n : need] = new_ids
        self._mat[self._n : need] = vectors
        self._n = need

    def _snapshot(self, model: str) -> tuple[np.ndarray, np.ndarray]:
        """(ids, matrix) of every vector made by `model`. Rows are never changed in place, so the arrays stay valid while scoring."""
        with self._cache_lock:
            if self._cache_model != model:
                with self.db.lock:
                    rows = self.db.conn.execute("SELECT frame_id, vec FROM frame_vectors WHERE model = ?", (model,)).fetchall()
                ids = np.fromiter((r["frame_id"] for r in rows), dtype=np.int64, count=len(rows))
                dim = len(rows[0]["vec"]) // 2 if rows else 0
                mat = np.zeros((len(rows), dim), dtype=np.float16)
                for i, r in enumerate(rows):
                    blob = r["vec"]
                    if len(blob) == dim * 2:
                        mat[i] = np.frombuffer(blob, dtype="<f2")
                self._ids, self._mat, self._n, self._cache_model = ids, mat, len(rows), model
                with self._pending_lock:
                    self._pending_deletes.clear()  # the load already reflects every committed delete
            else:
                self._apply_deletes()
            return self._ids[: self._n], self._mat[: self._n]

    def counts(self) -> dict:
        model = self.model_id()
        with self.db.lock:
            total = int(self.db.conn.execute("SELECT COUNT(*) AS n FROM frames WHERE image_path <> ''").fetchone()["n"])
            indexed = int(self.db.conn.execute("SELECT COUNT(*) AS n FROM frame_vectors WHERE model = ?", (model,)).fetchone()["n"])
            other = int(self.db.conn.execute("SELECT COUNT(*) AS n FROM frame_vectors WHERE model <> ?", (model,)).fetchone()["n"])
        return {"total": total, "indexed": indexed, "stale": other}

    def has_vectors(self) -> bool:
        with self.db.lock:
            return self.db.conn.execute("SELECT 1 FROM frame_vectors WHERE model = ? LIMIT 1", (self.model_id(),)).fetchone() is not None

    def vector_of(self, frame_id: int, model: str) -> np.ndarray | None:
        with self.db.lock:
            row = self.db.conn.execute("SELECT vec FROM frame_vectors WHERE frame_id = ? AND model = ?", (frame_id, model)).fetchone()
        if row is None or not row["vec"] or len(row["vec"]) % 2:
            return None
        return np.frombuffer(row["vec"], dtype="<f2").astype(np.float32)

    def reindex(self) -> int:
        """Forget every vector; the indexer starts again from the newest frame."""
        with self.db.lock:
            removed = self.db.conn.execute("DELETE FROM frame_vectors").rowcount
        self._drop_cache()
        self.failed.clear()
        self._wake.set()
        return removed

    # ------------------------------------------------------------------ indexer
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="argus-visual", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def wake(self) -> None:
        self._wake.set()

    def on_settings_changed(self) -> None:
        if not self.enabled():
            self.unload()
        self._wake.set()

    def missing(self, model: str, limit: int) -> list[int]:
        """Newest frames with a stored image and no vector of this model, skipping the ones that failed this session."""
        skip = len(self.failed)
        with self.db.lock:
            rows = self.db.conn.execute(
                """SELECT f.id FROM frames f LEFT JOIN frame_vectors v ON v.frame_id = f.id AND v.model = ?
                   WHERE v.frame_id IS NULL AND f.image_path <> '' ORDER BY f.captured_at DESC LIMIT ?""",
                (model, limit + skip),
            ).fetchall()
        return [r["id"] for r in rows if r["id"] not in self.failed][:limit]

    def _load_images(self, ids: list[int]) -> tuple[list[int], list[Image.Image]]:
        good, images = [], []
        for fid in ids:
            info = self.frames.image_file(fid)
            try:
                if not info or not info[0].exists():
                    raise FileNotFoundError("image file missing")
                with Image.open(info[0]) as handle:
                    handle.load()
                    images.append(handle.convert("RGB"))
                good.append(fid)
            except Exception as error:
                if len(self.failed) < MAX_FAILED:
                    self.failed.add(fid)
                self.last_error = f"frame {fid}: {type(error).__name__}: {error}"[:200]
        return good, images

    def index_batch(self, limit: int = BATCH) -> int:
        """Embed up to `limit` missing frames; returns how many were stored. Public so tests can drive it without the thread."""
        engine = self.engine()
        if engine is None:
            return 0
        ids = self.missing(engine.model_id, limit)
        if not ids:
            return 0
        good, images = self._load_images(ids)
        if not good:
            return len(ids)  # all failed and are now skipped: the caller should look again at once, not sleep
        started = time.perf_counter()
        vectors = engine.embed_images(images)
        per_image = (time.perf_counter() - started) * 1000.0 / len(good)
        self.put_vectors(good, vectors, engine.model_id)
        self.avg_ms = round(per_image if self.avg_ms is None else self.avg_ms * 0.9 + per_image * 0.1, 1)
        self.indexed_session += len(good)
        return len(good)

    def _run(self) -> None:
        _lower_thread_priority()
        while not self._stop.is_set():
            if not self.usable():
                self.working = False
                self._wake.wait(IDLE_POLL_S)
                self._wake.clear()
                continue
            if self.busy() > 0:  # OCR has work: it goes first
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            started = time.perf_counter()
            try:
                done = self.index_batch()
            except Exception as error:
                self.last_error = f"{type(error).__name__}: {error}"[:200]
                log.warning("visual indexing failed: %s", self.last_error)
                done = 0
            self.working = done > 0
            if done == 0:
                if self._embedder is not None and time.monotonic() - self._last_used > IDLE_UNLOAD_S:
                    self.unload()  # nothing to index and nobody searching for a while: free the model's memory
                self._wake.wait(IDLE_POLL_S)  # nothing missing (or the model is not loadable): look again in a few seconds
                self._wake.clear()
                continue
            spent = time.perf_counter() - started
            self._stop.wait(max(0.05, spent * (1.0 / self.duty - 1.0)))  # duty cycle: leave the CPU alone the rest of the time

    # ------------------------------------------------------------------ download
    def start_download(self) -> dict:
        if self.kind() != "auto":
            return {**self.download, "state": "error", "error": f"visual backend is {self.kind()!r}: nothing to download"}
        with self._download_lock:
            if self.download["state"] == "downloading":
                return dict(self.download)
            if visual_model.model_present(self.directory):
                self.download = {"state": "done", "file": None, "done": 0, "total": 0, "error": None}
                self._wake.set()
                return dict(self.download)
            self.download = {"state": "downloading", "file": None, "done": 0, "total": 0, "error": None}
            threading.Thread(target=self._download, name="argus-visual-download", daemon=True).start()
            return dict(self.download)

    def _download(self) -> None:
        def progress(name: str, done: int, total: int) -> None:
            self.download.update({"file": name, "done": done, "total": total})

        try:
            visual_model.download_model(self.directory, progress)
            self.download = {"state": "done", "file": None, "done": 0, "total": 0, "error": None}
        except Exception as error:
            self.download = {"state": "error", "file": None, "done": 0, "total": 0, "error": str(error)[:300]}
            log.warning("visual model download failed: %s", error)
        self.engine_error = None
        self._wake.set()

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        counts = self.counts()
        ready = self.model_ready()
        engine = self._embedder
        active = self.usable()
        pending = max(0, counts["total"] - counts["indexed"] - len(self.failed)) if active else 0
        return {
            "enabled": self.enabled(),
            "backend": self.kind(),
            "available": ready,
            "active": active,
            "model": visual_model.MODEL_LABEL if self.kind() == "auto" else (engine.label if engine else self.model_id()),
            "model_id": self.model_id(),
            "model_bytes": visual_model.model_bytes(self.directory) if self.kind() == "auto" else 0,
            "model_dir": str(self.directory),
            "device": "cpu",
            "threads": getattr(engine, "threads", int(os.environ.get("ARGUS_VISUAL_THREADS", "1") or 1)),
            "indexed": counts["indexed"],
            "total": counts["total"],
            "stale": counts["stale"],
            "pending": pending,
            "failed": len(self.failed),
            "indexing": bool(self.working and pending),
            "indexed_this_session": self.indexed_session,
            "ms_per_frame": self.avg_ms,
            "last_error": self.engine_error or self.last_error,
            "download": dict(self.download),
        }

    # ------------------------------------------------------------------ search
    @staticmethod
    def _score(snapshot: tuple[np.ndarray, np.ndarray], query: np.ndarray, allowed: set[int] | None, k: int) -> tuple[list[tuple[int, float]], dict]:
        """The `k` best (frame id, cosine) and {n, mean, std} of every score considered."""
        ids, mat = snapshot
        q = np.asarray(query, dtype=np.float32)
        if not len(ids) or mat.shape[1] != q.shape[0]:
            return [], {"n": 0, "mean": 0.0, "std": 0.0}
        scores = np.empty(len(ids), dtype=np.float32)
        step = 32768
        for start in range(0, len(ids), step):
            scores[start : start + step] = mat[start : start + step].astype(np.float32) @ q
        if allowed is not None:
            scores = np.where(np.isin(ids, np.fromiter(allowed, dtype=np.int64, count=len(allowed))), scores, -np.inf)
        finite = scores[np.isfinite(scores)]
        k = min(k, len(finite))
        if k <= 0:
            return [], {"n": 0, "mean": 0.0, "std": 0.0}
        top = np.argpartition(-scores, k - 1)[:k]
        best = sorted(((int(ids[i]), float(scores[i])) for i in top), key=lambda t: (-t[1], t[0]))
        return best, {"n": len(finite), "mean": float(finite.mean()), "std": float(finite.std())}

    def _allowed(self, start: float | None, end: float | None, app: str | None) -> set[int] | None:
        clauses, params = self.queries._range_clause(start, end, app)
        if not clauses:
            return None
        with self.db.lock:
            rows = self.db.conn.execute(f"SELECT f.id FROM frames f WHERE {' AND '.join(clauses)}", params).fetchall()
        return {r["id"] for r in rows}

    def _moments(self, scored: list[tuple[int, float]], window_s: int = 600) -> list[dict]:
        """Fold scored frames into moments (consecutive frames of one app + window). `visual_score` is the best cosine of a moment."""
        if not scored:
            return []
        ids = [fid for fid, _ in scored]
        rows: dict[int, object] = {}
        with self.db.lock:
            for i in range(0, len(ids), 400):
                chunk = ids[i : i + 400]
                marks = ",".join("?" * len(chunk))
                for r in self.db.conn.execute(f"SELECT f.* FROM frames f WHERE f.id IN ({marks})", chunk).fetchall():
                    rows[r["id"]] = r
        ranked = []
        for fid, score in scored:
            r = rows.get(fid)
            if r is not None:
                ranked.append((Candidate(fid, float(r["captured_at"]), r["app"], r["window_title"], "", "", dict(r)), -score))
        moments = group_moments(ranked, window_s)
        best_ids = [m["best"].id for m in moments]
        texts: dict[int, str] = {}
        with self.db.lock:
            for i in range(0, len(best_ids), 400):
                chunk = best_ids[i : i + 400]
                marks = ",".join("?" * len(chunk))
                for r in self.db.conn.execute(f"SELECT rowid AS id, text FROM frames_fts WHERE rowid IN ({marks})", chunk).fetchall():
                    texts[r["id"]] = r["text"] or ""
        out = []
        for m in moments:
            best = m["best"]
            out.append({
                **_frame_row(best.row),
                "snippet": _excerpt(texts.get(best.id, ""), 160),
                "rank": round(m["rank"], 4),
                "visual_score": round(-m["rank"], 4),
                "first_at": iso_local(m["first_at"]),
                "last_at": iso_local(m["last_at"]),
                "count": m["count"],
                "frame_ids": m["frame_ids"],
                "duration_s": round(sum(max(0.0, float(c.row["until_at"]) - float(c.row["captured_at"])) for c, _ in m["members"]), 1),
                "via": ["visual"],
            })
        return out

    def visual_moments(self, q: str, start: float | None, end: float | None, app: str | None, relevant_only: bool) -> tuple[list[dict], dict]:
        engine = self.engine()
        if engine is None:
            return [], {"used": False, "reason": self._why_not()}
        t0 = time.perf_counter()
        qvec = engine.embed_text(q)
        t1 = time.perf_counter()
        scored, stats = self._score(self._snapshot(engine.model_id), qvec, self._allowed(start, end, app), CANDIDATES)
        best = scored[0][1] if scored else None
        if relevant_only and scored:
            floor = max(MIN_ABS, scored[0][1] - REL)
            if stats["n"] >= Z_MIN_FRAMES:
                floor = max(floor, stats["mean"] + Z * stats["std"])
            scored = [s for s in scored if s[1] >= floor]
        moments = self._moments(scored)
        t2 = time.perf_counter()
        info = {"used": True, "reason": None, "model": engine.model_id, "frames_scored": len(scored), "embed_ms": round((t1 - t0) * 1000, 1),
                "search_ms": round((t2 - t1) * 1000, 1), "best_score": round(best, 4) if best is not None else None}
        return moments, info

    def _why_not(self) -> str:
        if not self.enabled():
            return "La búsqueda visual está desactivada en Ajustes."
        if not self.model_ready():
            return "Falta descargar el modelo de búsqueda visual (Ajustes, Búsqueda visual)."
        return f"El modelo visual no se pudo cargar: {self.engine_error or 'error desconocido'}"

    def search(self, q: str, start: float | None, end: float | None, app: str | None, limit: int, mode: str = "both") -> dict:
        """OCR search, visual search or both fused by rank. `both` quietly falls back to text when there is no visual index yet."""
        mode = mode if mode in MODES else "both"
        if mode == "text":
            return {**self.queries.search(q, start, end, app, limit), "mode": "text", "visual": {"used": False, "reason": None}}
        if mode == "both" and not (self.usable() and self.has_vectors()):
            usable = self.usable()
            return {**self.queries.search(q, start, end, app, limit), "mode": "text",
                    "visual": {"used": False, "reason": None if usable else self._why_not(), "indexing": usable}}
        if mode == "visual":
            moments, info = self.visual_moments(q, start, end, app, relevant_only=False)
            if not info["used"]:
                raise VisualUnavailable(info["reason"])
            return {"query": q, "hits": moments[:limit], "frames_total": sum(m["count"] for m in moments), "moments_total": len(moments),
                    "mode": "visual", "visual": info}
        wide = max(limit, 50)
        text = self.queries.search(q, start, end, app, wide)
        moments, info = self.visual_moments(q, start, end, app, relevant_only=True)
        fused = fuse_hits(text["hits"], moments, wide)
        return {"query": q, "match": text.get("match"), "hits": fused[:limit], "mode": "both", "visual": info,
                "frames_total": text.get("frames_total", 0) + sum(m["count"] for m in moments), "moments_total": len(fused)}

    def similar(self, frame_id: int, limit: int, start: float | None = None, end: float | None = None, app: str | None = None,
                same_moment: bool = False) -> dict:
        """Frames that look like `frame_id`, folded into moments; the moment the frame belongs to is left out unless `same_moment`."""
        engine = self.engine()
        if engine is None:
            raise VisualUnavailable(self._why_not())
        if self.frames.image_file(frame_id) is None:
            raise LookupError(f"Frame {frame_id} does not exist (it may have been deleted by retention).")
        vec = self.vector_of(frame_id, engine.model_id)
        if vec is None:  # not indexed yet: embed it now, it costs one image
            good, images = self._load_images([frame_id])
            if not good:
                raise LookupError(f"Frame {frame_id} has no readable image.")
            vec = engine.embed_images(images)[0]
            self.put_vectors([frame_id], vec[None, :], engine.model_id)
        t0 = time.perf_counter()
        scored, _ = self._score(self._snapshot(engine.model_id), vec, self._allowed(start, end, app), CANDIDATES + 1)
        moments = self._moments(scored)
        if not same_moment:
            moments = [m for m in moments if frame_id not in m["frame_ids"]]
        for m in moments:
            m["frame_ids"] = [f for f in m["frame_ids"] if f != frame_id]
            m["count"] = len(m["frame_ids"])
        moments = [m for m in moments if m["count"]]
        return {"frame_id": frame_id, "hits": moments[:limit], "moments_total": len(moments), "frames_total": sum(m["count"] for m in moments),
                "mode": "similar", "visual": {"used": True, "reason": None, "model": engine.model_id,
                                              "search_ms": round((time.perf_counter() - t0) * 1000, 1)}}
