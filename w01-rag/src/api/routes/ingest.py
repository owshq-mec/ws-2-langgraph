"""POST /api/v1/ingest — trigger a background ingestion run."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


async def _ingest_job(app, job_id: str) -> None:
    """Run the ingestion pipeline holding the per-app ingest lock."""
    lock: asyncio.Lock = app.state.ingest_lock
    started = datetime.now(timezone.utc)
    app.state.last_ingest_job = {
        "job_id": job_id,
        "status": "running",
        "started_at": started.isoformat(),
        "finished_at": None,
        "nodes_indexed": None,
        "error": None,
    }
    log.info("ingest job %s started", job_id)

    async with lock:
        try:
            # Imported lazily so the API process doesn't pull the full LlamaIndex
            # ingestion stack until someone actually triggers an ingest.
            from src.ingestion.config import IngestionConfig
            from src.ingestion.pipeline import build_pipeline, run_pipeline
            from src.ingestion.readers import MongoDBReader, SeaweedFSReader

            cfg = IngestionConfig()
            docs = SeaweedFSReader(cfg).load_data() + MongoDBReader(cfg).load_data()
            if not docs:
                app.state.last_ingest_job.update(
                    status="completed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    nodes_indexed=0,
                )
                log.info("ingest job %s finished: 0 documents to index", job_id)
                return

            pipeline = build_pipeline(cfg)
            nodes = await run_pipeline(pipeline, docs)
            app.state.last_ingest_job.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                nodes_indexed=len(nodes),
            )
            log.info("ingest job %s finished: %d nodes indexed", job_id, len(nodes))
        except Exception as exc:
            log.exception("ingest job %s failed", job_id)
            app.state.last_ingest_job.update(
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(req: Request) -> dict:
    """Trigger a re-ingestion of all data sources into the Memory engine.

    Runs in the background and returns immediately. Use GET /api/v1/ingest/status
    to poll the most recent job.
    """
    lock: asyncio.Lock = req.app.state.ingest_lock
    if lock.locked():
        prior = req.app.state.last_ingest_job or {}
        raise HTTPException(
            status_code=409,
            detail={"message": "ingestion already in progress", "current_job": prior},
        )

    job_id = f"ingest-{uuid.uuid4().hex[:12]}"
    asyncio.create_task(_ingest_job(req.app, job_id))
    return {
        "status": "ingestion_started",
        "job_id": job_id,
        "message": "Ingestion running in background. Poll /api/v1/ingest/status for progress.",
    }


@router.get("/ingest/status")
async def ingest_status(req: Request) -> dict:
    """Return the status of the most recent ingestion job (or `null` if none)."""
    return {"current_job": req.app.state.last_ingest_job}
