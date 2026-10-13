"""API routers."""

from .agent import router as agent_router
from .frames import router as frames_router
from .imports import router as imports_router
from .status import router as status_router
from .visual import router as visual_router

ROUTERS = [status_router, frames_router, visual_router, imports_router, agent_router]
