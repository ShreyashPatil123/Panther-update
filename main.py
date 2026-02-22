"""Main entry point for NVIDIA AI Agent — web edition."""
import asyncio
import sys
import webbrowser
from pathlib import Path

from loguru import logger

from src.config import load_config
from src.core.agent import AgentOrchestrator
from src.utils.logging_config import setup_logging
from src.utils.secure_storage import get_api_key, get_google_api_key


async def main():
    """Main application entry point."""
    Path("./data").mkdir(exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)

    setup_logging(level="INFO")
    logger.info("Starting PANTHER AI Agent (web mode)")

    config = load_config()

    try:
        orchestrator = AgentOrchestrator(config)
        await orchestrator.initialize()

        # API key priority: keyring > .env
        stored_key = get_api_key()
        if config.ollama_enabled:
            logger.info("Ollama mode active — skipping NVIDIA API key setup")
        elif stored_key:
            logger.info("Found API key in secure storage (keyring)")
            orchestrator.set_api_key(stored_key)
        elif config.nvidia_api_key and config.nvidia_api_key != "your_api_key_here":
            logger.info("Using API key from .env configuration")
        else:
            logger.warning(
                "No NVIDIA API key found. Please set it via the Settings button in the UI."
            )

        stored_google_key = get_google_api_key()
        if stored_google_key:
            config.google_api_key = stored_google_key

        # Create FastAPI app
        from web.server import create_app
        app = create_app(config, orchestrator)

        import uvicorn
        host = "127.0.0.1"
        port = 8765

        # Open browser after a short delay so the server is ready
        async def _open_browser():
            await asyncio.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        asyncio.create_task(_open_browser())

        logger.info(f"PANTHER web UI → http://{host}:{port}")

        config_uv = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",
        )
        server = uvicorn.Server(config_uv)
        await server.serve()

    except Exception:
        logger.exception("Fatal error during startup")
        raise


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception:
        logger.exception("Application failed to start")
        sys.exit(1)
