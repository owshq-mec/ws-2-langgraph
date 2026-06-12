"""FastAPI application factory for the DataOps Knowledge Hub."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import health, ingest, query
from src.engines.router import RouterEngine

log = logging.getLogger(__name__)

APP_VERSION = "1.0.0"

DESCRIPTION = """\
Enterprise RAG over heterogeneous data stores.

The Knowledge Hub answers questions by routing them across three engines:

- **Ledger** (PostgreSQL) — text-to-SQL for facts, counts, and aggregations
- **Memory** (Qdrant) — vector search for policies, runbooks, and historical events
- **Brain** (Neo4j) — Cypher traversal for ownership, dependencies, and lineage

Complex questions are decomposed into sub-questions, executed in parallel, and
synthesized into a single answer with per-source provenance.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the RouterEngine at startup; close it at shutdown."""
    log.info("Starting Knowledge Hub API v%s — initializing RouterEngine…", APP_VERSION)
    app.state.start_time = time.time()
    app.state.router = RouterEngine()
    app.state.ingest_lock = asyncio.Lock()
    app.state.last_ingest_job = None
    log.info("RouterEngine ready.")
    try:
        yield
    finally:
        log.info("Shutting down — closing RouterEngine…")
        app.state.router.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="DataOps Knowledge Hub",
        description=DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # CORS — wide open for dev/workshop. Restrict in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing middleware.
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "%s %s -> %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Process-Time-ms"] = f"{elapsed_ms:.2f}"
        return response

    # Exception handlers.
    @app.exception_handler(asyncio.TimeoutError)
    async def timeout_handler(_request: Request, _exc: asyncio.TimeoutError):
        return JSONResponse(
            status_code=504,
            content={"detail": "Upstream query timed out."},
        )

    @app.exception_handler(Exception)
    async def catchall_handler(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )

    # Routes.
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(ingest.router)

    return app
