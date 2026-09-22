"""Process-level configuration read from the environment (never from the DB)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .guard import parse_allowed_hosts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5183


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    """Everything the process needs before the database exists."""

    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    port: int = DEFAULT_PORT
    port_strict: bool = False
    capture_backend: str = "auto"  # auto | mss | fake | none
    window_backend: str = "auto"  # auto | windows | fake | none
    autostart: bool = True  # start the recorder thread with the app
    allowed_hosts: tuple[str, ...] = ()  # extra Host values (exact or *.suffix) besides localhost
    data_dir_configured: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "argus-hoard.db"

    @property
    def frames_dir(self) -> Path:
        return self.data_dir / "frames"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "mcp-token"

    @classmethod
    def from_env(cls) -> "Config":
        raw_dir = _env("ARGUS_DATA_DIR")
        port_raw = _env("ARGUS_PORT") or _env("PORT") or str(DEFAULT_PORT)
        try:
            port = int(port_raw)
        except ValueError:
            port = DEFAULT_PORT
        if not 1 <= port <= 65535:
            port = DEFAULT_PORT
        return cls(
            data_dir=Path(raw_dir).expanduser() if raw_dir else REPO_ROOT / "data",
            port=port,
            port_strict=_env("PORT_STRICT") == "1",
            capture_backend=_env("ARGUS_CAPTURE", "auto") or "auto",
            window_backend=_env("ARGUS_WINDOW", "auto") or "auto",
            autostart=_env("ARGUS_AUTOSTART", "1") != "0",
            allowed_hosts=parse_allowed_hosts(_env("ARGUS_ALLOWED_HOSTS")),
            data_dir_configured=bool(raw_dir),
        )
