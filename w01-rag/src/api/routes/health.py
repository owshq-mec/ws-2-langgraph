"""GET /health — per-service connectivity check.

Each backend is probed with a hard 5-second deadline. Probes run in parallel
so the endpoint returns in worst-case ~5s, not 5 × N.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

import httpx
from fastapi import APIRouter, Request
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.engines.config import EngineConfig
from src.ingestion.config import IngestionConfig
from src.schemas.api import HealthResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_PROBE_TIMEOUT = 5.0
_CRITICAL = {"postgres", "qdrant", "neo4j"}


# ---------------------------------------------------------------------------
# Per-service probes (sync; wrapped in asyncio.to_thread by the runner)
# ---------------------------------------------------------------------------

def _probe_postgres(cfg: EngineConfig) -> None:
    engine = create_engine(cfg.postgres_connection_string, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def _probe_qdrant_sync(cfg: EngineConfig) -> None:
    url = f"http://{cfg.qdrant_host}:{cfg.qdrant_port}/healthz"
    with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
        client.get(url).raise_for_status()


def _probe_neo4j(cfg: EngineConfig) -> None:
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        with driver.session() as session:
            session.run("RETURN 1").consume()
    finally:
        driver.close()


def _probe_mongo(cfg: IngestionConfig) -> None:
    client: MongoClient | None = None
    try:
        client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=int(_PROBE_TIMEOUT * 1000))
        client.admin.command("ping")
    finally:
        if client is not None:
            client.close()


def _probe_seaweedfs_sync(cfg: IngestionConfig) -> None:
    # Master status, not S3 — same endpoint the init scripts wait on.
    url = f"http://{cfg.seaweedfs_host}:9333/cluster/status"
    with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
        client.get(url).raise_for_status()


# ---------------------------------------------------------------------------
# Probe runner with timeout + exception classification
# ---------------------------------------------------------------------------

_EXPECTED_PROBE_ERRORS = (
    SQLAlchemyError,
    Neo4jError,
    ServiceUnavailable,
    PyMongoError,
    httpx.HTTPError,
    OSError,
)


async def _run_probe(name: str, probe: Callable[[], None]) -> tuple[str, str]:
    try:
        await asyncio.wait_for(asyncio.to_thread(probe), timeout=_PROBE_TIMEOUT)
        return name, "healthy"
    except asyncio.TimeoutError:
        log.warning("health: %s timed out after %.1fs", name, _PROBE_TIMEOUT)
        return name, "unhealthy"
    except _EXPECTED_PROBE_ERRORS as exc:
        log.warning("health: %s failed: %s", name, exc)
        return name, "unhealthy"


@router.get("/health", response_model=HealthResponse)
async def health_check(req: Request) -> HealthResponse:
    """Check the health of all connected services with a 5-second budget each.

    Overall status is `healthy` only when all critical stores
    (postgres, qdrant, neo4j) are healthy.
    """
    engine_cfg = EngineConfig()
    ingest_cfg = IngestionConfig()

    probes: dict[str, Callable[[], None]] = {
        "postgres":  lambda: _probe_postgres(engine_cfg),
        "qdrant":    lambda: _probe_qdrant_sync(engine_cfg),
        "neo4j":     lambda: _probe_neo4j(engine_cfg),
        "mongo":     lambda: _probe_mongo(ingest_cfg),
        "seaweedfs": lambda: _probe_seaweedfs_sync(ingest_cfg),
    }

    results = await asyncio.gather(*(_run_probe(n, p) for n, p in probes.items()))
    services = dict(results)

    if all(services.get(s) == "healthy" for s in _CRITICAL):
        overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"
    else:
        overall = "unhealthy"

    uptime = max(0.0, time.time() - getattr(req.app.state, "start_time", time.time()))

    return HealthResponse(
        status=overall,
        services=services,
        uptime_seconds=round(uptime, 2),
        version=req.app.version,
    )
