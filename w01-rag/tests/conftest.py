"""Shared fixtures and pytest configuration."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def config():
    """Engine configuration loaded from .env. Integration tests only."""
    # Imported here, not at module top, so unit tests don't pay the
    # `EngineConfig` (and transitively, llama-index) import cost.
    from src.engines.config import EngineConfig

    return EngineConfig()


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Base URL for FastAPI integration tests."""
    return os.getenv("API_BASE_URL", "http://localhost:8000")
