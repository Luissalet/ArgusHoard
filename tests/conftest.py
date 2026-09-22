import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from argus.config import Config  # noqa: E402
from argus.main import create_app  # noqa: E402
from argus.services import Services  # noqa: E402


def make_config(tmp_path: Path, **overrides) -> Config:
    base = dict(data_dir=tmp_path / "data", capture_backend="fake", window_backend="fake", autostart=False, data_dir_configured=True)
    base.update(overrides)
    return Config(**base)


@pytest.fixture
def services(tmp_path):
    svc = Services(make_config(tmp_path))
    yield svc
    svc.stop()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    app = create_app(make_config(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.services = app.state.services
        yield test_client


def wait_ocr(svc: Services, frame_ids, timeout: float = 60.0) -> None:
    """Block until every id has left the pending state (OCR is real, ~0.5 s per frame)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = set(svc.frames.pending_frames(limit=1000))
        if not pending.intersection(frame_ids):
            return
        time.sleep(0.1)
    raise AssertionError(f"OCR did not finish for {frame_ids}")


def ticks(svc: Services, count: int, start: float | None = None, interval: int = 5) -> list[int]:
    """Drive the recorder synchronously; return every stored frame id."""
    start = start or time.time() - count * interval
    stored: list[int] = []
    for index in range(count):
        stored.extend(svc.recorder.tick(now=start + index * interval).stored)
    return stored
