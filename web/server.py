"""FastAPI application factory."""
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from web.routes.chat import router as chat_router
from web.routes.settings import router as settings_router
from web.routes.models import router as models_router
from web.routes.compare import router as compare_router
from web.routes.panther_live import router as panther_live_router


def create_app(config, orchestrator) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application settings (src.config.Settings)
        orchestrator: Initialized AgentOrchestrator instance
    """
    app = FastAPI(title="PANTHER AI Agent", version="1.0.0")

    # Store shared state
    app.state.config = config
    app.state.orchestrator = orchestrator

    # CORS (allows the browser to talk to the API during dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(chat_router)
    app.include_router(settings_router)
    app.include_router(models_router)
    app.include_router(compare_router)
    app.include_router(panther_live_router)

    # Static files (CSS, JS, assets)
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Serve pages
    @app.get("/")
    async def serve_index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/compare")
    async def serve_compare():
        return FileResponse(str(static_dir / "compare.html"))

    @app.on_event("startup")
    async def _startup():
        logger.info("PANTHER web server starting up")

    @app.on_event("shutdown")
    async def _shutdown():
        logger.info("PANTHER web server shutting down")
        await orchestrator.close()

    return app
