"""API routers."""

from .agent import router as agent_router
from .frames import router as frames_router
from .pwa import router as pwa_router
from .status import router as status_router

ROUTERS = [status_router, frames_router, pwa_router, agent_router]
