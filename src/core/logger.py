"""Centralised, safe logging for the verification bot."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
APPLICATION_LOGGER_NAME = "verification_bot"


def setup_logging(
    config: Config,
    *,
    log_directory: str | Path = "logs",
) -> logging.Logger:
    """Configure and return the application's root logger.

    Console output is useful during development.  A rotating file keeps a
    limited local history without letting logs grow forever.  The function is
    idempotent, so integration tests and reloads cannot add duplicate handlers.
    """
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    logger.setLevel(_parse_level(config.log_level))
    logger.propagate = False

    if getattr(logger, "_verification_bot_configured", False):
        return logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logger.level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    directory = Path(log_directory)
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        directory / "verification_bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Library logs can be useful in development but noisy in normal operation.
    logging.getLogger("discord").setLevel(logging.DEBUG if config.debug else logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    setattr(logger, "_verification_bot_configured", True)
    logger.info("Logging configured at %s level.", logging.getLevelName(logger.level))
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the application logger or one of its named child loggers."""
    if not name:
        return logging.getLogger(APPLICATION_LOGGER_NAME)
    return logging.getLogger(f"{APPLICATION_LOGGER_NAME}.{name}")


def _parse_level(level_name: str) -> int:
    """Convert a validated config value to a standard logging level."""
    level = logging.getLevelNamesMapping().get(level_name.upper())
    if isinstance(level, int):
        return level
    raise ValueError(f"Unsupported log level: {level_name}")
