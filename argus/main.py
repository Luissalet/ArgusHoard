"""FastAPI application factory: request guard, API routers, PWA files, static SPA. The guard, the error envelope, the
health route, the PWA files and the single-page-app server are the shared `hoard_link.guard` / `hoard_link.service`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import __version__
from .api import ROUTERS
from .config import Config
from .hoard_link import family
from .hoard_link.guard import install_guard
from .hoard_link.service import health_router, install_error_handlers, install_pwa, install_spa
from .services import Services

STATIC_DIR = Path(__file__).resolve().parent / "static"
SERVICE = "argus-hoard"


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = Services(config)
        app.state.services = services
        services.start()
        logging.getLogger("argus").info("Argus's Hoard %s — data in %s", __version__, config.data_dir)
        try:
            yield
        finally:
            services.stop()

    app = FastAPI(title="Argus's Hoard", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    # Hoard Link 0.4: this app on the family bus (agent.call events, calls to
    # siblings through the hub, the hoard_link block in /api/health).
    family.configure("argus", str(config.data_dir), token_file=str(config.token_path))

    install_guard(app, port_getter=lambda: config.port, allowed_hosts=config.allowed_hosts, allowed_env="ARGUS_ALLOWED_HOSTS")
    install_error_handlers(app)
    app.include_router(health_router(SERVICE, __version__, extra=lambda: {"dataDirConfigured": config.data_dir_configured}))
    for router in ROUTERS:
        app.include_router(router)
    install_pwa(app, name="Argus's Hoard", short_name="Argus's Hoard", theme="#4a3f8f", background="#fbfafd",
                cache="argus-hoard-assets", lang="es", static_dir=STATIC_DIR, version=__version__)
    install_spa(app, STATIC_DIR)
    return app
