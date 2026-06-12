"""Integration tests for the three query engines.

Require the full stack running and (for Ledger/Memory) data populated:
  - Postgres has customers + orders rows  → data-generator is running
  - Qdrant has the `dataops-memory` collection  → `make ingest` has run
  - Neo4j has been seeded  → `init-neo4j` ran on startup
"""
from __future__ import annotations

import pytest

from src.schemas.query import (
    BrainQueryResult,
    LedgerQueryResult,
    MemoryQueryResult,
)


@pytest.mark.integration
class TestLedgerEngine:
    @pytest.mark.asyncio
    async def test_count_query(self, config):
        from src.engines.ledger import LedgerEngine
        engine = LedgerEngine(config)
        try:
            result = await engine.query("How many customers are there?")
            assert isinstance(result, LedgerQueryResult)
            assert "SELECT" in result.sql_query_executed.upper()
            assert result.row_count >= 0
        finally:
            engine.close()

    @pytest.mark.asyncio
    async def test_aggregation_query(self, config):
        from src.engines.ledger import LedgerEngine
        engine = LedgerEngine(config)
        try:
            result = await engine.query("What is the total revenue from completed orders?")
            assert isinstance(result, LedgerQueryResult)
            assert "completed" in result.sql_query_executed.lower()
        finally:
            engine.close()


@pytest.mark.integration
class TestMemoryEngine:
    @pytest.mark.asyncio
    async def test_policy_query(self, config):
        from src.engines.memory import MemoryEngine
        engine = MemoryEngine(config)
        try:
            result = await engine.query("What is the data retention policy for PII?")
            assert isinstance(result, MemoryQueryResult)
            assert result.confidence > 0.0
            assert len(result.sources) > 0
        finally:
            engine.close()

    @pytest.mark.asyncio
    async def test_event_query(self, config):
        from src.engines.memory import MemoryEngine
        engine = MemoryEngine(config)
        try:
            result = await engine.query("What pipeline failures happened recently?")
            assert isinstance(result, MemoryQueryResult)
        finally:
            engine.close()


@pytest.mark.integration
class TestBrainEngine:
    @pytest.mark.asyncio
    async def test_ownership_query(self, config):
        from src.engines.brain import BrainEngine
        engine = BrainEngine(config)
        try:
            result = await engine.query("What pipelines does team-billing own?")
            assert isinstance(result, BrainQueryResult)
            assert "MATCH" in result.cypher_query_executed.upper()
        finally:
            engine.close()

    @pytest.mark.asyncio
    async def test_dependency_query(self, config):
        from src.engines.brain import BrainEngine
        engine = BrainEngine(config)
        try:
            result = await engine.query("What would be impacted if the orders table goes down?")
            assert isinstance(result, BrainQueryResult)
            assert result.dependency_chain is not None
        finally:
            engine.close()
