"""Query-engine output contracts — used as `output_cls` for LlamaIndex
query engines so the LLM is forced to return validated structured JSON."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.schemas.domain import DependencyChain

__all__ = [
    "LedgerQueryResult",
    "MemoryQueryResult",
    "BrainQueryResult",
    "SynthesizedResponse",
]


class LedgerQueryResult(BaseModel):
    """Structured result from a Ledger (Text-to-SQL) query."""

    sql_query_executed: str = Field(description="The SQL query that was generated and executed")
    summary: str = Field(description="Natural language summary of the SQL result")
    row_count: int = Field(description="Number of rows returned")
    data_points: list[dict] = Field(default_factory=list, description="Key data points extracted")


class MemoryQueryResult(BaseModel):
    """Structured result from a Memory (Vector Search) query."""

    summary: str = Field(description="Synthesized answer from retrieved documents")
    sources: list[str] = Field(default_factory=list, description="Source document names/paths")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score of the retrieval"
    )
    relevant_facts: list[str] = Field(default_factory=list, description="Key facts extracted")


class BrainQueryResult(BaseModel):
    """Structured result from a Brain (Graph Traversal) query."""

    cypher_query_executed: str = Field(
        description="The Cypher query that was generated and executed"
    )
    summary: str = Field(description="Natural language summary of the graph result")
    nodes_traversed: int = Field(description="Number of nodes visited")
    relationships_found: list[str] = Field(
        default_factory=list, description="Key relationships discovered"
    )
    dependency_chain: Optional[DependencyChain] = Field(
        default=None, description="Downstream dependency chain when relevant"
    )


class SynthesizedResponse(BaseModel):
    """The final synthesized response combining results from multiple engines."""

    answer: str = Field(description="Complete synthesized answer to the user's question")
    sub_questions: list[str] = Field(
        default_factory=list, description="Sub-questions that were generated"
    )
    sources_consulted: list[str] = Field(
        description="Which engines were consulted: ledger, memory, brain"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence score")
    recommendation: Optional[str] = Field(
        default=None, description="Actionable recommendation if applicable"
    )
