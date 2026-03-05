"""Entry point for the PD3r API server.

Usage:
    poetry run pd3r-api              # Start API server
    uvicorn src.api.app:app --reload # Development with auto-reload
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from src.config.settings import get_settings


def main():
    # Persist WARNING+ logs to a rotating file for post-mortem debugging
    Path("output/logs").mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        "output/logs/api.log", maxBytes=5_000_000, backupCount=3
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)

    settings = get_settings()
    uvicorn.run(
        "src.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
