"""Main entry point for NVIDIA AI Agent — web edition."""
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from loguru import logger

from src.config import load_config
from src.core.agent import AgentOrchestrator
from src.utils.logging_config import setup_logging
from src.utils.secure_storage import get_api_key, get_google_api_key


# ── Browser launcher with CDP support ────────────────────────────────────────

CDP_PORT = 9222


def _find_browser() -> str | None:
    """Find Chrome or Edge executable on the system."""
    # Windows common paths
    candidates = [
        # Edge (most common on Windows)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # Fallback: check PATH
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _launch_browser_with_cdp(url: str) -> subprocess.Popen | None:
    """Launch user's browser with remote debugging enabled."""
    browser_path = _find_browser()
    if not browser_path:
        logger.warning("No Chrome/Edge found — falling back to default browser")
        import webbrowser
        webbrowser.open(url)
        return None

    user_data_dir = str(Path("./data/browser_profile").resolve())
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    args = [
        browser_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--remote-allow-origins=*",
        "--remote-debugging-address=127.0.0.1",
        url,
    ]
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Browser launched with CDP on port {CDP_PORT}: {os.path.basename(browser_path)}")
        return proc
    except Exception as e:
        logger.error(f"Failed to launch browser with CDP: {e}")
        import webbrowser
        webbrowser.open(url)
        return None


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

        # Store CDP URL as env var for TaskDispatcher to read
        os.environ["CDP_URL"] = f"http://127.0.0.1:{CDP_PORT}"

        # Launch browser with CDP after a short delay
        browser_proc = None

        async def _open_browser():
            nonlocal browser_proc
            await asyncio.sleep(1.5)
            browser_proc = _launch_browser_with_cdp(f"http://{host}:{port}")

        asyncio.create_task(_open_browser())

        logger.info(f"PANTHER web UI -> http://{host}:{port}")

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
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception:
        logger.exception("Application failed to start")
        sys.exit(1)
