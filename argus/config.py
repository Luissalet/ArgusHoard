"""Process-level configuration read from the environment (never from the DB)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .hoard_link.appconfig import env_flag, env_int, env_str
from .hoard_link.guard import parse_allowed_hosts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5183


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
        raw_dir = env_str("ARGUS_DATA_DIR")
        port = env_int("ARGUS_PORT", "PORT")
        if port is None or not 1 <= port <= 65535:
            port = DEFAULT_PORT
        return cls(
            data_dir=Path(raw_dir).expanduser() if raw_dir else REPO_ROOT / "data",
            port=port,
            port_strict=env_flag("PORT_STRICT"),
            capture_backend=env_str("ARGUS_CAPTURE", "auto") or "auto",
            window_backend=env_str("ARGUS_WINDOW", "auto") or "auto",
            autostart=env_flag("ARGUS_AUTOSTART", True),
            allowed_hosts=parse_allowed_hosts(env_str("ARGUS_ALLOWED_HOSTS")),
            data_dir_configured=bool(raw_dir),
        )
