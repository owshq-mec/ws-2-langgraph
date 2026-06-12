"""Integration tests for the RouterEngine end-to-end flow."""
from __future__ import annotations

import pytest

from src.schemas.query import SynthesizedResponse


@pytest.mark.integration
class TestRouterEngine:
    @pytest.mark.asyncio
    async def test_single_engine_routing(self, config):
        from src.engines.router import RouterEngine
        router = RouterEngine(config)
        try:
            response, sources = await router.query("How many enterprise customers?")
            assert isinstance(response, SynthesizedResponse)
            assert len(sources) >= 1
            # The router can decompose into 1+ sub-questions; what we assert is
            # that ledger was at least one of the sources consulted.
            assert any(s.source == "ledger" for s in sources)
        finally:
            router.close()

    @pytest.mark.asyncio
    async def test_multi_engine_routing(self, config):
        from src.engines.router import RouterEngine
        router = RouterEngine(config)
        try:
            response, sources = await router.query(
                "What are the top customers by revenue, what's the SLA for billing, "
                "and what depends on the orders table?"
            )
            assert isinstance(response, SynthesizedResponse)
            assert len(sources) >= 2
            assert len(response.sub_questions) >= 2
        finally:
            router.close()

    @pytest.mark.asyncio
    async def test_forced_routing(self, config):
        from src.engines.router import RouterEngine
        router = RouterEngine(config)
        try:
            response, sources = await router.query(
                "Tell me everything about billing",
                sources=["ledger", "brain"],
            )
            assert all(s.source in {"ledger", "brain"} for s in sources)
            assert set(response.sources_consulted) == {"ledger", "brain"}
        finally:
            router.close()
