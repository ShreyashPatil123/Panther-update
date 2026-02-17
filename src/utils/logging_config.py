"""Logging configuration for NVIDIA AI Agent."""
import sys
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO", log_dir: Path = Path("./logs")):
    """Configure logging with console and file handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console logging with colored output
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
    )

    # File logging for all messages
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation="500 MB",
        retention="10 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        compression="zip",
    )

    # Separate error log
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        rotation="100 MB",
        retention="30 days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging configured with level: {level}")
