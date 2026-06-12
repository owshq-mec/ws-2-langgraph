"""RouterEngine — the orchestrator across Ledger / Memory / Brain.

Pipeline per call:
  1. Classify  — LLM decomposes the question into 1–3 sub-questions, each
                 tagged with the engine it should hit.  Skipped when the
                 caller passes an explicit `sources` filter.
  2. Execute   — sub-questions run in parallel against their engines.
  3. Synthesize — LLM merges the per-engine results into a final answer
                  plus an optional actionable recommendation.

All LLM calls use structured output (Pydantic via `as_structured_llm`) so we
never parse freeform JSON.  Per-engine failures are caught and surfaced as
unavailable sources — the router never fails the whole query because one
backend is down.
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Sequence

from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field

from src.engines.brain import BrainEngine
from src.engines.config import EngineConfig
from src.engines.ledger import LedgerEngine
from src.engines.memory import MemoryEngine
from src.schemas.api import SourceDetail
from src.schemas.query import (
    BrainQueryResult,
    LedgerQueryResult,
    MemoryQueryResult,
    SynthesizedResponse,
)

log = logging.getLogger(__name__)

__all__ = ["RouterEngine"]


# ---------------------------------------------------------------------------
# Internal LLM-output schemas (private to this module)
# ---------------------------------------------------------------------------

class _EngineName(str, Enum):
    LEDGER = "ledger"
    MEMORY = "memory"
    BRAIN = "brain"


class _SubQuestion(BaseModel):
    engine: _EngineName = Field(description="Which engine should answer this sub-question")
    question: str = Field(description="A self-contained question for that engine")


class _Classification(BaseModel):
    sub_questions: list[_SubQuestion] = Field(
        description="1 to 3 sub-questions, one per relevant engine"
    )


class _Synthesis(BaseModel):
    answer: str = Field(description="Final synthesized answer to the original question")
    recommendation: Optional[str] = Field(
        default=None,
        description="One short actionable recommendation if applicable; null otherwise",
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """\
You are a query router for a DataOps Knowledge Hub with 3 data stores.

1. LEDGER (PostgreSQL) — customers, orders, products tables.
   Use for: numerical questions, counts, aggregations, revenue, top-N,
   filtering by status/plan/date.
   Examples: "How many enterprise customers?", "Total revenue this month?",
   "Top 5 customers by spend".

2. MEMORY (Qdrant vector store) — data retention policies, SLA definitions,
   incident runbooks, data dictionaries, pipeline event logs, user activity logs.
   Use for: policy questions, procedure questions, "what happened" questions,
   historical events, definitions.
   Examples: "What is the retention policy for PII?",
   "What's the SLA for etl_billing_daily?",
   "What happened in the last failure?".

3. BRAIN (Neo4j graph) — pipelines, tables, dashboards, teams, and the
   relationships OWNS / READS_FROM / WRITES_TO / FEEDS / USED_BY.
   Use for: relationship questions, dependency/lineage questions, ownership,
   impact analysis, "what connects to what".
   Examples: "Who owns the billing pipeline?",
   "What's impacted if orders table goes down?",
   "Show lineage of fact_revenue".

Rules:
- Simple questions that clearly belong to one engine → return 1 sub-question.
- Complex questions that span multiple domains → decompose into 2–3
  sub-questions, one per relevant engine.
- Never return more than 3 sub-questions.
- Rephrase each sub-question to be self-contained and specific to that
  engine's data.
"""

_SYNTHESIZE_SYSTEM = """\
You synthesize answers for a DataOps Knowledge Hub.

Given the original question and one or more sub-question results from
specialised engines (ledger, memory, brain), produce:
- a clear answer that integrates the evidence,
- an optional one-sentence actionable recommendation when the data warrants
  it (otherwise leave recommendation null).

If a source was unavailable, acknowledge it briefly without speculating.
"""


# ---------------------------------------------------------------------------
# Engine result container
# ---------------------------------------------------------------------------

class _EngineRun(BaseModel):
    """Internal record of one engine invocation."""
    engine: _EngineName
    sub_question: str
    result: object | None = None  # LedgerQueryResult | MemoryQueryResult | BrainQueryResult | None
    error: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class RouterEngine:
    """Orchestrates Ledger / Memory / Brain behind a single async API."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self._llm = OpenAI(model=self.config.llm_model)
        self._classify_llm = self._llm.as_structured_llm(_Classification)
        self._synth_llm = self._llm.as_structured_llm(_Synthesis)

        # Per-engine instantiation is best-effort. A failure here (e.g. Qdrant
        # collection missing) doesn't kill the router — that engine is just
        # reported as unavailable on every query that targets it.
        self.ledger = self._safe_init("ledger", LedgerEngine, self.config)
        self.memory = self._safe_init("memory", MemoryEngine, self.config)
        self.brain = self._safe_init("brain", BrainEngine, self.config)

    @staticmethod
    def _safe_init(name: str, cls, config: EngineConfig):
        try:
            return cls(config)
        except Exception as exc:
            log.warning("RouterEngine: %s engine unavailable at startup: %s", name, exc)
            return None

    def _engine_for(self, name: _EngineName):
        return {
            _EngineName.LEDGER: self.ledger,
            _EngineName.MEMORY: self.memory,
            _EngineName.BRAIN: self.brain,
        }[name]

    # ---- Step 1: Classification ----

    async def _classify(self, question: str) -> list[_SubQuestion]:
        messages = [
            ChatMessage(role="system", content=_CLASSIFY_SYSTEM),
            ChatMessage(role="user", content=question),
        ]
        try:
            response = await self._classify_llm.achat(messages)
            classification: _Classification = response.raw  # type: ignore[assignment]
            sub_qs = classification.sub_questions[:3]
        except Exception as exc:
            log.warning("Classification failed (%s) — falling back to all engines", exc)
            sub_qs = []

        if not sub_qs:
            # Fallback: ask all three engines the original question.
            sub_qs = [
                _SubQuestion(engine=_EngineName.LEDGER, question=question),
                _SubQuestion(engine=_EngineName.MEMORY, question=question),
                _SubQuestion(engine=_EngineName.BRAIN, question=question),
            ]
        return sub_qs

    # ---- Step 2: Execution ----

    async def _run_one(self, sub: _SubQuestion) -> _EngineRun:
        engine = self._engine_for(sub.engine)
        if engine is None:
            return _EngineRun(
                engine=sub.engine,
                sub_question=sub.question,
                error=f"{sub.engine.value} engine is unavailable",
            )
        try:
            result = await engine.query(sub.question)
            return _EngineRun(engine=sub.engine, sub_question=sub.question, result=result)
        except Exception as exc:
            log.exception("Engine %s raised during query", sub.engine.value)
            return _EngineRun(
                engine=sub.engine,
                sub_question=sub.question,
                error=str(exc),
            )

    async def _execute(self, sub_qs: Sequence[_SubQuestion]) -> list[_EngineRun]:
        return await asyncio.gather(*(self._run_one(sq) for sq in sub_qs))

    # ---- Step 3: Synthesis ----

    @staticmethod
    def _format_for_synthesis(question: str, runs: Sequence[_EngineRun]) -> str:
        lines = [f"Original question: {question}", "", "Sub-question results:"]
        for r in runs:
            lines.append(f"\n— Engine: {r.engine.value}")
            lines.append(f"  Sub-question: {r.sub_question}")
            if r.error is not None:
                lines.append(f"  Status: UNAVAILABLE ({r.error})")
                continue
            res = r.result
            if isinstance(res, LedgerQueryResult):
                lines.append(f"  SQL: {res.sql_query_executed}")
                lines.append(f"  Rows: {res.row_count}")
                lines.append(f"  Summary: {res.summary}")
                if res.data_points:
                    lines.append(f"  Sample rows: {res.data_points[:5]}")
            elif isinstance(res, MemoryQueryResult):
                lines.append(f"  Sources: {res.sources}")
                lines.append(f"  Confidence: {res.confidence:.2f}")
                lines.append(f"  Summary: {res.summary}")
            elif isinstance(res, BrainQueryResult):
                lines.append(f"  Cypher: {res.cypher_query_executed}")
                lines.append(f"  Nodes touched: {res.nodes_traversed}")
                lines.append(f"  Summary: {res.summary}")
                if res.dependency_chain is not None:
                    dc = res.dependency_chain
                    lines.append(
                        f"  Dependency chain from {dc.source}: "
                        f"pipelines={dc.downstream_pipelines}, "
                        f"tables={dc.downstream_tables}, "
                        f"dashboards={dc.downstream_dashboards}, "
                        f"teams={dc.impacted_teams}"
                    )
            else:
                lines.append(f"  Result: {res!r}")
        return "\n".join(lines)

    async def _synthesize(self, question: str, runs: Sequence[_EngineRun]) -> _Synthesis:
        body = self._format_for_synthesis(question, runs)
        messages = [
            ChatMessage(role="system", content=_SYNTHESIZE_SYSTEM),
            ChatMessage(role="user", content=body),
        ]
        try:
            response = await self._synth_llm.achat(messages)
            return response.raw  # type: ignore[return-value]
        except Exception as exc:
            log.warning("Synthesis failed (%s) — returning concatenated summaries", exc)
            fallback = "\n\n".join(
                self._fallback_summary(r) for r in runs if r.error is None and r.result is not None
            ) or "No engine returned a result."
            return _Synthesis(answer=fallback, recommendation=None)

    @staticmethod
    def _fallback_summary(run: _EngineRun) -> str:
        res = run.result
        header = f"[{run.engine.value}] "
        if isinstance(res, (LedgerQueryResult, MemoryQueryResult, BrainQueryResult)):
            return header + (res.summary or "(no summary)")
        return header + repr(res)

    # ---- Step 4: SourceDetail builders ----

    @staticmethod
    def _build_source_detail(run: _EngineRun) -> SourceDetail:
        if run.error is not None or run.result is None:
            return SourceDetail(
                source=run.engine.value,
                data_store={"ledger": "postgresql", "memory": "qdrant", "brain": "neo4j"}[run.engine.value],
                query_used="",
                result_summary=f"UNAVAILABLE: {run.error or 'no result'}",
                confidence=0.0,
            )
        res = run.result
        if isinstance(res, LedgerQueryResult):
            return SourceDetail(
                source="ledger",
                data_store="postgresql",
                query_used=res.sql_query_executed,
                result_summary=res.summary,
                confidence=0.9,  # SQL is deterministic
            )
        if isinstance(res, MemoryQueryResult):
            return SourceDetail(
                source="memory",
                data_store="qdrant",
                query_used="Vector search (top_k=5)",
                result_summary=res.summary,
                confidence=res.confidence,
            )
        if isinstance(res, BrainQueryResult):
            return SourceDetail(
                source="brain",
                data_store="neo4j",
                query_used=res.cypher_query_executed,
                result_summary=res.summary,
                confidence=0.85,  # Cypher is deterministic, synthesis isn't
            )
        raise TypeError(f"Unknown result type from engine {run.engine.value}: {type(res)!r}")

    # ---- Public API ----

    async def query(
        self,
        question: str,
        sources: list[str] | None = None,
    ) -> tuple[SynthesizedResponse, list[SourceDetail]]:
        """Route, execute, and synthesize an answer.

        Args:
            question: Natural language question from the user.
            sources: Optional engine filter (e.g. ["ledger", "brain"]). When
                provided, classification is skipped and each named engine
                receives the original question.

        Returns:
            Tuple of (SynthesizedResponse, list[SourceDetail]).
        """
        started = time.perf_counter()

        # Step 1 — classification (or honour explicit source filter).
        if sources:
            try:
                requested = [_EngineName(s.lower()) for s in sources]
            except ValueError as exc:
                raise ValueError(
                    f"Invalid source in {sources}; allowed: ledger, memory, brain"
                ) from exc
            sub_qs = [_SubQuestion(engine=e, question=question) for e in requested]
        else:
            sub_qs = await self._classify(question)

        # Step 2 — parallel execution.
        runs = await self._execute(sub_qs)

        # Step 3 — synthesis.
        synth = await self._synthesize(question, runs)

        # Step 4 — assemble outputs.
        source_details = [self._build_source_detail(r) for r in runs]
        good_confidences = [sd.confidence for sd, r in zip(source_details, runs) if r.error is None]
        confidence = (
            max(0.0, min(1.0, sum(good_confidences) / len(good_confidences)))
            if good_confidences
            else 0.0
        )

        response = SynthesizedResponse(
            answer=synth.answer,
            sub_questions=[sq.question for sq in sub_qs],
            sources_consulted=[r.engine.value for r in runs],
            confidence=confidence,
            recommendation=synth.recommendation,
        )

        log.info(
            "router: question=%r engines=%s elapsed=%.2fs",
            question,
            [r.engine.value for r in runs],
            time.perf_counter() - started,
        )
        return response, source_details

    # ---- Lifecycle ----

    def close(self) -> None:
        for engine in (self.ledger, self.memory, self.brain):
            if engine is not None:
                try:
                    engine.close()
                except Exception:
                    pass
