"""The image/text embedder behind visual search: a small CLIP pair run on the CPU with onnxruntime.

Two ONNX towers that live in the same 512-dimensional space:

* image: OpenAI CLIP ViT-B/32 vision tower with float16 weights (about 168 MB on disk; onnxruntime widens them to float32 on load, so
  it ranks exactly like the full float32 model, which is 335 MB. The int8 build is half the size again but ranked clearly worse on
  screenshots, see the README);
* text: `clip-ViT-B-32-multilingual-v1` (a multilingual DistilBERT distilled onto the CLIP text space, 50+ languages,
  Spanish included), int8-quantised (about 129 MB; its ranking is the same as the float32 one), plus its 768 -> 512 projection (1.5 MB).

No torch, no transformers, no new dependency: onnxruntime, numpy and Pillow are already Argus requirements. The tokenizer (BERT
WordPiece, cased) is implemented below so the text tower needs nothing else. The model files (about 300 MB in total) are downloaded
once, on request, into `<data>/models/clip-b32-multilingual/`; until they are there visual search is simply "not available".

CPU only, on purpose: the session is created with the CPU provider alone and `CUDA_VISIBLE_DEVICES=-1` is set before onnxruntime
loads, so a machine with a GPU never sees Argus on it. One intra-op thread by default (`ARGUS_VISUAL_THREADS`): inference then runs on
the calling thread, which is the one the indexer lowers the priority of.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import numpy as np
from PIL import Image

log = logging.getLogger("argus.visual")

MODEL_DIR_NAME = "clip-b32-multilingual"
MODEL_ID = "clip-vit-b32-multilingual-v1-vf16-ti8"
MODEL_LABEL = "CLIP ViT-B/32 multilingüe"
DIM = 512
IMAGE_SIZE = 224
PAD_COLOUR = (127, 127, 127)
TEXT_MAX_TOKENS = 128
IMAGE_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
IMAGE_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

HF = "https://huggingface.co"


@dataclass(frozen=True)
class ModelFile:
    local: str
    url: str
    size: int  # expected bytes, used for the progress bar and to spot a truncated download


FILES: tuple[ModelFile, ...] = (
    ModelFile("vision.onnx", f"{HF}/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_fp16.onnx", 0),
    ModelFile("text.onnx", f"{HF}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/onnx/model_quint8_avx2.onnx", 0),
    ModelFile("dense.safetensors", f"{HF}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/2_Dense/model.safetensors", 0),
    ModelFile("vocab.txt", f"{HF}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/vocab.txt", 0),
)
MANIFEST = "manifest.json"


def model_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "models" / MODEL_DIR_NAME


def model_present(directory: Path) -> bool:
    """True when every file of the model is on disk (the manifest is written last, after all of them)."""
    directory = Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if manifest.get("model") != MODEL_ID:
        return False
    return all((directory / f.local).is_file() and (directory / f.local).stat().st_size > 0 for f in FILES)


def model_bytes(directory: Path) -> int:
    total = 0
    for f in FILES:
        try:
            total += (Path(directory) / f.local).stat().st_size
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------------------------------------------- download
class DownloadError(RuntimeError):
    pass


def download_model(directory: Path, progress: Callable[[str, int, int], None] | None = None, *, timeout: float = 60.0) -> None:
    """Fetch the model files into `directory` (skipping the ones already complete), then write the manifest.

    `progress(file, bytes_done_of_this_file, bytes_total_of_this_file)`. Each file is written to `<name>.part` and renamed when whole,
    so an interrupted download never leaves a file that looks finished. Raises `DownloadError`."""
    import httpx

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, int] = {}
    for spec in FILES:
        target = directory / spec.local
        marker = directory / (spec.local + ".ok")  # remembers which URL the finished file came from, so a changed model is fetched again
        if target.is_file() and target.stat().st_size > 0 and marker.is_file() and marker.read_text(encoding="utf-8").strip() == spec.url:
            sizes[spec.local] = target.stat().st_size
            continue
        part = directory / (spec.local + ".part")
        try:
            with httpx.stream("GET", spec.url, follow_redirects=True, timeout=timeout) as response:
                if response.status_code != 200:
                    raise DownloadError(f"{spec.url} answered {response.status_code}")
                total = int(response.headers.get("content-length") or 0)
                done = 0
                with part.open("wb") as handle:
                    for chunk in response.iter_bytes(1 << 20):
                        handle.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(spec.local, done, total)
                if total and done != total:
                    raise DownloadError(f"{spec.local}: got {done} of {total} bytes")
        except DownloadError:
            part.unlink(missing_ok=True)
            raise
        except Exception as error:  # network, disk
            part.unlink(missing_ok=True)
            raise DownloadError(f"{spec.local}: {type(error).__name__}: {error}") from error
        os.replace(part, target)
        marker.write_text(spec.url, encoding="utf-8")
        sizes[spec.local] = target.stat().st_size
    (directory / MANIFEST).write_text(json.dumps({"model": MODEL_ID, "files": sizes}, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------- tokenizer
def _is_punct(ch: str) -> bool:
    cp = ord(ch)
    if 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126:
        return True
    return unicodedata.category(ch).startswith("P")


def _is_cjk(cp: int) -> bool:
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F
            or 0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF or 0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F)


class WordPiece:
    """BERT's cased basic + WordPiece tokenizer (what the multilingual text tower was trained with)."""

    def __init__(self, vocab: dict[str, int], max_chars_per_word: int = 100):
        self.vocab = vocab
        self.unk = vocab["[UNK]"]
        self.cls = vocab["[CLS]"]
        self.sep = vocab["[SEP]"]
        self.pad = vocab.get("[PAD]", 0)
        self.max_chars = max_chars_per_word

    @classmethod
    def from_file(cls, path: Path) -> "WordPiece":
        vocab: dict[str, int] = {}
        with open(path, encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                vocab[line.rstrip("\r\n")] = index
        return cls(vocab)

    @staticmethod
    def _basic(text: str) -> list[str]:
        cleaned = []
        for ch in text:
            cp = ord(ch)
            if cp == 0 or cp == 0xFFFD:
                continue
            category = unicodedata.category(ch)
            if ch in "\t\n\r" or category == "Zs":
                cleaned.append(" ")
            elif category in ("Cc", "Cf"):
                continue
            elif _is_cjk(cp):
                cleaned.append(f" {ch} ")
            else:
                cleaned.append(ch)
        out: list[str] = []
        for word in "".join(cleaned).split():
            current = ""
            for ch in word:
                if _is_punct(ch):
                    if current:
                        out.append(current)
                        current = ""
                    out.append(ch)
                else:
                    current += ch
            if current:
                out.append(current)
        return out

    def _pieces(self, word: str) -> list[int]:
        if len(word) > self.max_chars:
            return [self.unk]
        ids: list[int] = []
        start = 0
        while start < len(word):
            end = len(word)
            found = None
            while start < end:
                piece = word[start:end]
                if start > 0:
                    piece = "##" + piece
                if piece in self.vocab:
                    found = self.vocab[piece]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            ids.append(found)
            start = end
        return ids

    def encode(self, text: str, max_tokens: int = TEXT_MAX_TOKENS) -> list[int]:
        ids = [self.cls]
        for word in self._basic(text):
            ids.extend(self._pieces(word))
        ids = ids[: max_tokens - 1]
        ids.append(self.sep)
        return ids


# ---------------------------------------------------------------------------------------------------------------- engines
class Embedder(Protocol):
    model_id: str
    label: str
    dim: int
    device: str

    def embed_images(self, images: list[Image.Image]) -> np.ndarray: ...
    def embed_text(self, text: str) -> np.ndarray: ...


def _unit(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def read_safetensors(path: Path) -> dict[str, np.ndarray]:
    """Minimal safetensors reader (float32 only is needed here): 8-byte header length, JSON header, raw data."""
    raw = Path(path).read_bytes()
    (header_len,) = struct.unpack("<Q", raw[:8])
    header = json.loads(raw[8 : 8 + header_len])
    base = 8 + header_len
    out: dict[str, np.ndarray] = {}
    for name, info in header.items():
        if name == "__metadata__":
            continue
        start, end = info["data_offsets"]
        dtype = {"F32": "<f4", "F16": "<f2"}[info["dtype"]]
        out[name] = np.frombuffer(raw[base + start : base + end], dtype=dtype).reshape(info["shape"]).astype(np.float32)
    return out


def preprocess(image: Image.Image) -> np.ndarray:
    """CHW float32 for the vision tower. The whole screenshot is kept: scaled to 224 px on its long side and centred on a neutral grey
    square (letterbox). No centre crop (a crop of a 16:9 screen would throw the sides away, and a chart or a sidebar there is exactly what
    the user looks for) and no squeezing: on screenshots the letterbox ranked better than squashing to a square in both the int8 and the
    fp32 tower (see the README), because CLIP never saw distorted aspect ratios."""
    rgb = image.convert("RGB")
    scale = IMAGE_SIZE / max(rgb.width, rgb.height)
    resized = rgb.resize((max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), PAD_COLOUR)
    canvas.paste(resized, ((IMAGE_SIZE - resized.width) // 2, (IMAGE_SIZE - resized.height) // 2))
    array = (np.asarray(canvas, dtype=np.float32) / 255.0 - IMAGE_MEAN) / IMAGE_STD
    return array.transpose(2, 0, 1)


class ClipOnnxEmbedder:
    """The real embedder. Construction loads the four files; it raises if onnxruntime or a file is missing."""

    model_id = MODEL_ID
    label = MODEL_LABEL
    dim = DIM
    device = "cpu"

    def __init__(self, directory: Path, threads: int | None = None):
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # before onnxruntime looks at devices: Argus never uses a GPU
        import onnxruntime as ort

        threads = max(1, int(threads if threads is not None else os.environ.get("ARGUS_VISUAL_THREADS", "1") or 1))
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        self.threads = threads
        directory = Path(directory)
        self._vision = ort.InferenceSession(str(directory / "vision.onnx"), options, providers=["CPUExecutionProvider"])
        self._text = ort.InferenceSession(str(directory / "text.onnx"), options, providers=["CPUExecutionProvider"])
        self._vision_in = self._vision.get_inputs()[0].name
        self._vision_out = next((o.name for o in self._vision.get_outputs() if "embed" in o.name), self._vision.get_outputs()[0].name)
        self._text_inputs = {i.name for i in self._text.get_inputs()}
        dense = read_safetensors(directory / "dense.safetensors")
        self._dense = next(iter(dense.values()))  # (512, 768), no bias, identity activation
        self._tokenizer = WordPiece.from_file(directory / "vocab.txt")
        self._lock = threading.Lock()

    def embed_images(self, images: list[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, DIM), dtype=np.float32)
        batch = np.stack([preprocess(image) for image in images]).astype(np.float32)
        with self._lock:
            out = self._vision.run([self._vision_out], {self._vision_in: batch})[0]
        return _unit(out)

    def embed_text(self, text: str) -> np.ndarray:
        ids = self._tokenizer.encode(text or "")
        feed = {"input_ids": np.array([ids], dtype=np.int64), "attention_mask": np.ones((1, len(ids)), dtype=np.int64)}
        feed = {k: v for k, v in feed.items() if k in self._text_inputs}
        with self._lock:
            hidden = self._text.run([self._text.get_outputs()[0].name], feed)[0]  # (1, L, 768)
        pooled = hidden.mean(axis=1)  # every token is real (no padding in a batch of one)
        return _unit(pooled @ self._dense.T)[0]


class FakeEmbedder:
    """Deterministic stand-in for tests and the demo backend: no model, no download.

    Images become the mean colour (R, G, B) and a coarse 4x4 brightness grid; text maps colour words (English and Spanish) onto the same
    axes, and any other word to a stable pseudo-random direction. So "azul"/"blue" really is close to a blue frame."""

    model_id = "fake-colour-v1"
    label = "Embebedor de prueba (colores)"
    dim = 8
    device = "cpu"
    # word -> (red, green, blue, brightness)
    COLOURS = {
        "rojo": (1, 0, 0, 0), "roja": (1, 0, 0, 0), "red": (1, 0, 0, 0),
        "verde": (0, 1, 0, 0), "green": (0, 1, 0, 0),
        "azul": (0, 0, 1, 0), "blue": (0, 0, 1, 0),
        "blanco": (0, 0, 0, 1), "blanca": (0, 0, 0, 1), "white": (0, 0, 0, 1),
        "oscuro": (0, 0, 0, -1), "negro": (0, 0, 0, -1), "dark": (0, 0, 0, -1), "black": (0, 0, 0, -1),
    }

    def __init__(self, delay_s: float = 0.0):
        self.delay_s = delay_s
        self.calls = 0
        self.images_embedded = 0

    def _vector(self, rgb, bright: float = 0.0, extra: int = 0) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        v[0:3] = rgb
        v[3] = bright
        if extra:
            v[4 + (extra % 4)] = 1.0
        if not v.any():
            v[7] = 1.0
        return _unit(v)

    def embed_images(self, images: list[Image.Image]) -> np.ndarray:
        import time

        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s * len(images))
        rows = []
        for image in images:
            small = np.asarray(image.convert("RGB").resize((4, 4), Image.Resampling.BOX), dtype=np.float32) / 255.0
            mean = small.reshape(-1, 3).mean(axis=0)
            centred = mean - mean.mean()  # chroma: which channel dominates
            rows.append(self._vector(centred * 4.0, (float(mean.mean()) - 0.5) * 2.0))
            self.images_embedded += 1
        return np.stack(rows)

    def embed_text(self, text: str) -> np.ndarray:
        axes = np.zeros(4, dtype=np.float32)
        extra = 0
        for word in (text or "").lower().split():
            if word in self.COLOURS:
                axes += np.array(self.COLOURS[word], dtype=np.float32)
            else:
                extra += sum(ord(c) for c in word)
        return self._vector(axes[:3], float(axes[3]), extra if not axes.any() else 0)


def load_embedder(kind: str, data_dir: Path) -> Embedder | None:
    """`kind`: auto (the real model if its files are there), fake (tests/demos), none. None means "visual search not available"."""
    kind = (kind or "auto").lower()
    if kind == "none":
        return None
    if kind == "fake":
        return FakeEmbedder()
    directory = model_dir(data_dir)
    if not model_present(directory):
        return None
    return ClipOnnxEmbedder(directory)
