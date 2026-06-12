"""API contracts — request and response models for the FastAPI layer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

__all__ = [
    "QueryRequest",
    "SourceDetail",
    "QueryResponse",
    "HealthResponse",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    question: str = Field(
        description="The natural language question to ask the Knowledge Hub",
        json_schema_extra={
            "examples": [
                "How many enterprise customers do we have?",
                "What is the data retention policy for PII?",
                "What would be impacted if the orders table goes down?",
            ]
        },
    )
    sources: Optional[list[str]] = Field(
        default=None,
        description="Optionally restrict to specific sources: 'ledger', 'memory', 'brain'. None = all.",
        json_schema_extra={"examples": [["ledger"], ["brain", "memory"]]},
    )
    include_metadata: bool = Field(
        default=True,
        description="Whether to include sub-questions, SQL/Cypher queries, and source details",
    )


class SourceDetail(BaseModel):
    """Details about a specific source that was consulted."""

    source: str = Field(description="Engine name: ledger, memory, or brain")
    data_store: str = Field(description="Underlying store: postgresql, qdrant, or neo4j")
    query_used: str = Field(description="The actual query executed (SQL, vector search, or Cypher)")
    result_summary: str = Field(description="Summary of what this source returned")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this source's result")


class QueryResponse(BaseModel):
    """Response body for POST /query."""

    question: str = Field(description="The original question")
    answer: str = Field(description="Synthesized answer combining all sources")
    sub_questions: list[str] = Field(
        default_factory=list, description="How the question was decomposed"
    )
    sources_consulted: list[SourceDetail] = Field(description="Details per source")
    recommendation: Optional[str] = Field(default=None, description="Actionable recommendation")
    processing_time_ms: float = Field(description="Total processing time in milliseconds")
    timestamp: datetime = Field(
        default_factory=_utcnow,
        description="When the response was generated (UTC)",
    )


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str = Field(default="healthy", description="Overall health status")
    services: dict[str, str] = Field(
        description="Health status per service: postgres, qdrant, neo4j, seaweedfs"
    )
    uptime_seconds: float = Field(description="Process uptime in seconds")
    version: str = Field(description="Application version")
