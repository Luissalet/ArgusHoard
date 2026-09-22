"""OCR worker thread: consumes a queue of frame ids; capture never waits on it."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import OrderedDict

from PIL import Image

from .ocr import NullOcr, OcrBackend, select_ocr
from .store import FrameStore

log = logging.getLogger("argus.ocr")


class OcrWorker:
    def __init__(self, store: FrameStore, backend_name: str = "auto", language: str = "es", cache_size: int = 8):
        self.store = store
        self.backend_name = backend_name
        self.language = language
        self.queue: queue.Queue[int] = queue.Queue()
        self._images: OrderedDict[int, Image.Image] = OrderedDict()  # full-res images awaiting OCR
        self._queued: set[int] = set()  # ids in the queue, so the DB poll never double-processes them
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.engine: OcrBackend | None = None
        self.notes: list[str] = []
        self.processed = 0
        self.last_ms: int | None = None
        self.last_error: str | None = None

    # ---------- lifecycle ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="argus-ocr", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self.queue.put(-1)  # wake the loop
        if self._thread:
            self._thread.join(timeout)

    def reconfigure(self, backend_name: str, language: str) -> None:
        if backend_name != self.backend_name or language != self.language:
            self.backend_name, self.language = backend_name, language
            with self._lock:
                self.engine = None  # re-selected lazily by the worker thread

    def engine_name(self) -> str:
        return self.engine.name if self.engine else "starting"

    @property
    def depth(self) -> int:
        return self.queue.qsize()

    # ---------- submission ----------
    def submit(self, frame_id: int, image: Image.Image | None = None) -> None:
        with self._lock:
            self._queued.add(frame_id)
            if image is not None:
                self._images[frame_id] = image
                while len(self._images) > self._cache_size:
                    self._images.popitem(last=False)  # oldest falls back to the stored WebP
        self.queue.put(frame_id)

    # ---------- loop ----------
    def _ensure_engine(self) -> OcrBackend:
        with self._lock:
            if self.engine is None:
                self.engine, self.notes = select_ocr(self.backend_name, self.language)
                for note in self.notes:
                    log.info("ocr: %s", note)
            return self.engine

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                frame_id = self.queue.get(timeout=2.0)
            except queue.Empty:
                for pending in self.store.pending_frames(limit=5):  # leftovers from a previous run
                    with self._lock:
                        skip = pending in self._queued
                    if not skip:
                        self._process(pending)
                continue
            if frame_id < 0:
                break
            with self._lock:
                self._queued.discard(frame_id)
            self._process(frame_id)

    def process_now(self, frame_id: int) -> None:
        """Synchronous OCR of one frame (tests, selftest)."""
        self._process(frame_id)

    def _process(self, frame_id: int) -> None:
        with self._lock:
            image = self._images.pop(frame_id, None)
        scale = 1.0
        if image is None:
            info = self.store.image_file(frame_id)
            if not info or not info[0].exists():
                self.store.set_ocr_status(frame_id, "missing")
                return
            try:
                image = Image.open(info[0])
                image.load()
            except OSError as error:
                self.store.set_ocr_status(frame_id, "error")
                self.last_error = str(error)
                return
            scale = info[2] / image.width if image.width else 1.0  # blocks are kept in original pixels
        engine = self._ensure_engine()
        started = time.perf_counter()
        try:
            result = engine.recognise(image)
        except Exception as error:
            log.warning("ocr failed for frame %s: %s", frame_id, error)
            self.last_error = str(error)
            self.store.set_ocr_status(frame_id, "error", engine.name)
            return
        ms = int((time.perf_counter() - started) * 1000)
        if scale != 1.0:
            for block in result.blocks:
                block.x, block.y = int(block.x * scale), int(block.y * scale)
                block.w, block.h = int(block.w * scale), int(block.h * scale)
        if isinstance(engine, NullOcr):
            self.store.set_ocr_status(frame_id, "unavailable", engine.name)
        else:
            self.store.set_ocr_result(frame_id, result.blocks, result.text, ms, engine.name)
        self.processed += 1
        self.last_ms = ms
