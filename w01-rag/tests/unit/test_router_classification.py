"""Unit tests for RouterEngine routing logic.

The router's classification step is mocked at the method level — we test the
*routing decisions and execution wiring*, not the LLM that produces them.
No real backend connections are made: each engine is replaced with an
AsyncMock so we can assert what was called with what.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.query import (
    BrainQueryResult,
    LedgerQueryResult,
    MemoryQueryResult,
    SynthesizedResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger_result(summary: str = "ok") -> LedgerQueryResult:
    return LedgerQueryResult(
        sql_query_executed="SELECT 1", summary=summary, row_count=1, data_points=[],
    )


def _memory_result(summary: str = "ok") -> MemoryQueryResult:
    return MemoryQueryResult(summary=summary, sources=["doc.md"], confidence=0.8, relevant_facts=[])


def _brain_result(summary: str = "ok") -> BrainQueryResult:
    return BrainQueryResult(
        cypher_query_executed="MATCH (n) RETURN n",
        summary=summary,
        nodes_traversed=1,
        relationships_found=[],
        dependency_chain=None,
    )


@pytest.fixture
def router_with_mocked_engines():
    """Construct a RouterEngine where engine init is short-circuited."""
    # Import lazily so unit tests don't pay the cost when this fixture isn't used.
    from src.engines import router as router_module

    # Bypass engine construction (otherwise we'd hit Postgres/Qdrant/Neo4j).
    with patch.object(router_module.RouterEngine, "_safe_init", return_value=None):
        # Patch the LLM constructor so as_structured_llm doesn't try to hit OpenAI.
        with patch.object(router_module, "OpenAI") as fake_openai_cls:
            fake_llm = MagicMock()
            fake_llm.as_structured_llm.return_value = MagicMock()
            fake_openai_cls.return_value = fake_llm

            r = router_module.RouterEngine()

    # Now install AsyncMock engines so query() works.
    r.ledger = MagicMock()
    r.ledger.query = AsyncMock(return_value=_ledger_result())
    r.ledger.close = MagicMock()

    r.memory = MagicMock()
    r.memory.query = AsyncMock(return_value=_memory_result())
    r.memory.close = MagicMock()

    r.brain = MagicMock()
    r.brain.query = AsyncMock(return_value=_brain_result())
    r.brain.close = MagicMock()

    # Patch synthesis to a deterministic result so we test routing only.
    from src.engines.router import _Synthesis

    async def fake_synth(_question, _runs):
        return _Synthesis(answer="synthesized", recommendation=None)
    r._synthesize = fake_synth  # type: ignore[assignment]

    return r


def _patch_classification(router, sub_questions):
    """Replace router._classify with a function returning the given sub-questions."""
    async def fake_classify(_question):
        return sub_questions
    router._classify = fake_classify  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRouterClassification:
    @pytest.mark.asyncio
    async def test_routes_customers_question_to_ledger(self, router_with_mocked_engines):
        from src.engines.router import _EngineName, _SubQuestion
        r = router_with_mocked_engines
        _patch_classification(r, [_SubQuestion(engine=_EngineName.LEDGER, question="count customers")])

        response, sources = await r.query("How many customers?")
        assert isinstance(response, SynthesizedResponse)
        assert response.sources_consulted == ["ledger"]
        assert len(sources) == 1 and sources[0].source == "ledger"
        r.ledger.query.assert_awaited_once_with("count customers")
        r.memory.query.assert_not_awaited()
        r.brain.query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_routes_sla_question_to_memory(self, router_with_mocked_engines):
        from src.engines.router import _EngineName, _SubQuestion
        r = router_with_mocked_engines
        _patch_classification(r, [_SubQuestion(engine=_EngineName.MEMORY, question="sla for billing")])

        response, sources = await r.query("What is the SLA for etl_billing_daily?")
        assert response.sources_consulted == ["memory"]
        assert sources[0].source == "memory"
        r.memory.query.assert_awaited_once()
        r.ledger.query.assert_not_awaited()
        r.brain.query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_routes_ownership_question_to_brain(self, router_with_mocked_engines):
        from src.engines.router import _EngineName, _SubQuestion
        r = router_with_mocked_engines
        _patch_classification(r, [_SubQuestion(engine=_EngineName.BRAIN, question="who owns orders")])

        response, sources = await r.query("Who owns the orders table?")
        assert response.sources_consulted == ["brain"]
        assert sources[0].source == "brain"
        r.brain.query.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complex_question_decomposes_to_multiple_engines(self, router_with_mocked_engines):
        from src.engines.router import _EngineName, _SubQuestion
        r = router_with_mocked_engines
        _patch_classification(r, [
            _SubQuestion(engine=_EngineName.LEDGER, question="top customers by spend"),
            _SubQuestion(engine=_EngineName.MEMORY, question="retention policy"),
            _SubQuestion(engine=_EngineName.BRAIN,  question="impact of orders going down"),
        ])

        response, sources = await r.query("the WOW question")
        assert len(response.sub_questions) == 3
        assert set(response.sources_consulted) == {"ledger", "memory", "brain"}
        assert len(sources) == 3
        r.ledger.query.assert_awaited_once()
        r.memory.query.assert_awaited_once()
        r.brain.query.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_malformed_classification_falls_back_to_all_engines(self, router_with_mocked_engines):
        """When the LLM raises, _classify is supposed to fall back to all 3.
        We can't actually exercise the LLM here (it's mocked away in the fixture)
        — instead, we verify the fallback path of _classify directly.
        """
        r = router_with_mocked_engines

        # Force the classify_llm.achat to raise; check that the real _classify
        # returns the all-three fallback.
        r._classify_llm = MagicMock()
        r._classify_llm.achat = AsyncMock(side_effect=RuntimeError("bad json"))

        from src.engines.router import RouterEngine, _EngineName
        sub_qs = await RouterEngine._classify(r, "anything")
        assert len(sub_qs) == 3
        assert {sq.engine for sq in sub_qs} == {_EngineName.LEDGER, _EngineName.MEMORY, _EngineName.BRAIN}

    @pytest.mark.asyncio
    async def test_sources_filter_bypasses_classification(self, router_with_mocked_engines):
        r = router_with_mocked_engines

        # If sources is provided, _classify must NOT be called.
        called = {"classify": False}
        async def should_not_be_called(_q):
            called["classify"] = True
            raise AssertionError("_classify should be skipped when sources is given")
        r._classify = should_not_be_called  # type: ignore[assignment]

        response, sources = await r.query("anything", sources=["ledger", "brain"])
        assert called["classify"] is False
        assert {s.source for s in sources} == {"ledger", "brain"}
        assert response.sources_consulted == ["ledger", "brain"]

    @pytest.mark.asyncio
    async def test_invalid_source_raises_value_error(self, router_with_mocked_engines):
        r = router_with_mocked_engines
        with pytest.raises(ValueError, match="Invalid source"):
            await r.query("anything", sources=["not_an_engine"])
