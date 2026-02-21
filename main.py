"""Main entry point for NVIDIA AI Agent."""
import asyncio
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from loguru import logger

from src.config import load_config
from src.core.agent import AgentOrchestrator
from src.ui.main_window import MainWindow
from src.ui.themes import apply_dark_theme
from src.utils.logging_config import setup_logging
from src.utils.secure_storage import get_api_key, get_google_api_key


async def main():
    """Main application entry point."""
    # Create data directory
    Path("./data").mkdir(exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)

    # Setup logging
    setup_logging(level="INFO")
    logger.info("Starting NVIDIA AI Agent")

    # Load configuration
    config = load_config()
    logger.info(f"Configuration loaded from {config.db_path}")

    # Initialize Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("NVIDIA AI Agent")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("NVIDIA")

    # Apply dark theme
    apply_dark_theme(app)

    try:
        # Initialize Agent Orchestrator
        logger.info("Initializing agent orchestrator...")
        orchestrator = AgentOrchestrator(config)
        await orchestrator.initialize()

        # API key priority: keyring (secure storage) > .env file > not set
        stored_key = get_api_key()
        if stored_key:
            logger.info("Found API key in secure storage (keyring)")
            orchestrator.set_api_key(stored_key)
        elif config.nvidia_api_key and config.nvidia_api_key != "your_api_key_here":
            logger.info("Using API key from .env configuration")
            # Already set during orchestrator.initialize(), just log it
        else:
            logger.warning(
                "No NVIDIA API key found. Please set it via Settings dialog "
                "or add NVIDIA_API_KEY to your .env file."
            )

        # Google API key for Gemini Live voice (optional — only needed for mic)
        stored_google_key = get_google_api_key()
        if stored_google_key:
            logger.info("Found Google API key in secure storage (keyring)")
            config.google_api_key = stored_google_key
        elif config.google_api_key:
            logger.info("Using Google API key from .env configuration")
        else:
            logger.info(
                "No Google API key found. Gemini Live voice not available "
                "until configured in Settings."
            )

        # Create and show main window
        logger.info("Creating main window...")
        window = MainWindow(orchestrator)
        window.show()

        logger.info("Application started successfully")

        # Run event loop
        while True:
            app.processEvents()
            await asyncio.sleep(0.01)

    except Exception as e:
        logger.exception("Fatal error in main loop")
        raise

    finally:
        # Cleanup
        logger.info("Shutting down...")
        if "orchestrator" in locals():
            await orchestrator.close()


if __name__ == "__main__":
    try:
        # On Windows, use ProactorEventLoop for async support
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Application failed to start")
        sys.exit(1)
