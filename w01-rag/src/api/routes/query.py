"""POST /api/v1/query — the main query endpoint."""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from src.schemas.api import QueryRequest, QueryResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_hub(request: QueryRequest, req: Request) -> QueryResponse:
    """Route a question across the Ledger, Memory, and Brain engines.

    The system inspects the question, decomposes it into sub-questions if it
    spans multiple domains, runs the sub-questions in parallel against the
    relevant engines, and returns a synthesized answer with per-source
    provenance.
    """
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="`question` must not be empty.")

    router_engine = req.app.state.router

    started = time.perf_counter()
    try:
        synthesized, source_details = await router_engine.query(
            question=request.question,
            sources=request.sources,
        )
    except ValueError as exc:
        # Raised by RouterEngine for invalid `sources` values.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Upstream query timed out.") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000

    return QueryResponse(
        question=request.question,
        answer=synthesized.answer,
        sub_questions=synthesized.sub_questions,
        sources_consulted=source_details,
        recommendation=synthesized.recommendation,
        processing_time_ms=round(elapsed_ms, 2),
    )
