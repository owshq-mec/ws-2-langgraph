"""MemoryEngine — vector similarity search over Qdrant via LlamaIndex.

Connects to the existing `dataops-memory` collection (built by the ingestion
pipeline). Returns a `MemoryQueryResult` with sources, mean-score confidence,
and a short list of relevant facts.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from llama_index.core import VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from src.engines.config import EngineConfig
from src.schemas.query import MemoryQueryResult

log = logging.getLogger(__name__)

__all__ = ["MemoryEngine"]


def _source_label(metadata: dict[str, Any]) -> str:
    """Pick the best human-readable identifier from a node's metadata."""
    if "file_name" in metadata:
        return str(metadata["file_name"])
    collection = metadata.get("collection")
    if collection == "event_logs":
        return f"mongo:event_logs/{metadata.get('pipeline_name', 'unknown')}"
    if collection == "user_activity":
        return f"mongo:user_activity/{metadata.get('action', 'unknown')}"
    return metadata.get("source_type") or "unknown"


def _fact_from_node(node: Any) -> str:
    """Prefer the extractor-generated summary; fall back to the leading text."""
    md = node.metadata or {}
    summary = md.get("section_summary") or md.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    text = node.get_content() if hasattr(node, "get_content") else getattr(node, "text", "")
    text = (text or "").strip().replace("\n", " ")
    return text[:200] + ("…" if len(text) > 200 else "")


class MemoryEngine:
    """Vector-search engine over the Memory layer (Qdrant)."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        try:
            self._qdrant = QdrantClient(
                host=self.config.qdrant_host, port=self.config.qdrant_port
            )
            # Fail fast if collection is missing — the ingestion pipeline must run first.
            collections = {c.name for c in self._qdrant.get_collections().collections}
            if self.config.qdrant_collection not in collections:
                raise RuntimeError(
                    f"MemoryEngine: Qdrant collection "
                    f"'{self.config.qdrant_collection}' does not exist. "
                    "Run `make ingest` first."
                )
        except (UnexpectedResponse, OSError) as exc:
            raise RuntimeError(
                f"MemoryEngine: could not connect to Qdrant at "
                f"{self.config.qdrant_host}:{self.config.qdrant_port}: {exc}"
            ) from exc

        self._vector_store = QdrantVectorStore(
            client=self._qdrant, collection_name=self.config.qdrant_collection
        )
        self._embed_model = OpenAIEmbedding(model=self.config.embedding_model)
        self._llm = OpenAI(model=self.config.llm_model)
        self._index = VectorStoreIndex.from_vector_store(
            self._vector_store, embed_model=self._embed_model
        )
        self._engine = self._index.as_query_engine(
            similarity_top_k=5,
            response_mode="tree_summarize",
            llm=self._llm,
        )

    async def _query_once(self, question: str) -> MemoryQueryResult:
        try:
            response = await self._engine.aquery(question)
        except Exception as exc:
            log.exception("Memory query execution failed")
            return MemoryQueryResult(
                summary=f"Query failed: {exc}",
                sources=[],
                confidence=0.0,
                relevant_facts=[],
            )

        nodes = list(getattr(response, "source_nodes", []) or [])

        sources: list[str] = []
        scores: list[float] = []
        facts: list[str] = []
        seen_sources: set[str] = set()
        for sn in nodes:
            label = _source_label(sn.node.metadata or {})
            if label not in seen_sources:
                seen_sources.add(label)
                sources.append(label)
            if sn.score is not None:
                scores.append(max(0.0, min(1.0, float(sn.score))))
            fact = _fact_from_node(sn.node)
            if fact:
                facts.append(fact)

        confidence = sum(scores) / len(scores) if scores else 0.0

        return MemoryQueryResult(
            summary=str(response).strip(),
            sources=sources,
            confidence=confidence,
            relevant_facts=facts[:5],
        )

    async def query(self, question: str) -> MemoryQueryResult:
        try:
            return await asyncio.wait_for(
                self._query_once(question),
                timeout=self.config.query_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return MemoryQueryResult(
                summary=f"Query timed out after {self.config.query_timeout_seconds}s",
                sources=[],
                confidence=0.0,
                relevant_facts=[],
            )

    def close(self) -> None:
        try:
            self._qdrant.close()
        except Exception:
            pass
