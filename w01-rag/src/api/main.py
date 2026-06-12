"""Uvicorn entry point.  `uvicorn src.api.main:app` or `python -m src.api.main`."""
from __future__ import annotations

import logging

import uvicorn

from src.api.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
