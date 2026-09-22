"""`python -m argus` — run the app with uvicorn on 127.0.0.1."""

from __future__ import annotations

import logging
import os

import uvicorn

from . import __version__
from .config import Config
from .main import create_app
from .port import find_available_port


def main() -> None:
    level = os.environ.get("ARGUS_LOG", "warning").upper()
    logging.basicConfig(level=getattr(logging, level, logging.WARNING), format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = Config.from_env()
    port = config.port if config.port_strict else find_available_port(config.port)
    config.port = port
    app = create_app(config)
    print(f"Argus's Hoard {__version__} · http://127.0.0.1:{port} · datos en {config.data_dir}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
