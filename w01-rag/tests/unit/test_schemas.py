"""Unit tests for the Pydantic schema layer. No infrastructure required."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.api import HealthResponse, QueryRequest, QueryResponse, SourceDetail
from src.schemas.domain import (
    CustomerPlan,
    DependencyChain,
    OrderStatus,
    PipelineStatus,
    Severity,
)
from src.schemas.query import (
    BrainQueryResult,
    LedgerQueryResult,
    MemoryQueryResult,
    SynthesizedResponse,
)


# ---------------------------------------------------------------------------
# QueryRequest
# ---------------------------------------------------------------------------

class TestQueryRequest:
    def test_full_request(self):
        req = QueryRequest(
            question="How many customers do we have?",
            sources=["ledger"],
            include_metadata=True,
        )
        assert req.question == "How many customers do we have?"
        assert req.sources == ["ledger"]
        assert req.include_metadata is True

    def test_required_fields_only(self):
        req = QueryRequest(question="Anything?")
        assert req.question == "Anything?"
        assert req.sources is None
        assert req.include_metadata is True  # default

    def test_missing_question_raises(self):
        with pytest.raises(ValidationError):
            QueryRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# QueryResponse and SourceDetail
# ---------------------------------------------------------------------------

class TestQueryResponse:
    def test_full_response_with_source_details(self):
        details = [
            SourceDetail(
                source="ledger",
                data_store="postgresql",
                query_used="SELECT count(*) FROM customers",
                result_summary="5,000 customers",
                confidence=0.9,
            ),
            SourceDetail(
                source="brain",
                data_store="neo4j",
                query_used="MATCH (t:Team)-[:OWNS]->(p:Pipeline) RETURN p.name",
                result_summary="Team-billing owns 2 pipelines",
                confidence=0.85,
            ),
        ]
        resp = QueryResponse(
            question="combo?",
            answer="Synthesized answer.",
            sub_questions=["q1", "q2"],
            sources_consulted=details,
            recommendation=None,
            processing_time_ms=123.4,
        )
        assert len(resp.sources_consulted) == 2
        assert resp.timestamp.tzinfo is not None  # default factory yields tz-aware

    def test_source_detail_confidence_bounds(self):
        with pytest.raises(ValidationError):
            SourceDetail(
                source="ledger", data_store="postgresql",
                query_used="x", result_summary="y", confidence=1.5,
            )
        with pytest.raises(ValidationError):
            SourceDetail(
                source="ledger", data_store="postgresql",
                query_used="x", result_summary="y", confidence=-0.1,
            )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_customer_plan_values(self):
        assert {p.value for p in CustomerPlan} == {"free", "pro", "enterprise"}

    def test_order_status_values(self):
        assert {s.value for s in OrderStatus} == {"pending", "completed", "failed", "refunded"}

    def test_pipeline_status_values(self):
        assert {s.value for s in PipelineStatus} == {"completed", "failed", "warning"}

    def test_severity_values(self):
        assert {s.value for s in Severity} == {"info", "warning", "critical"}

    def test_enum_string_coercion(self):
        # Pydantic accepts the raw string and coerces to the enum.
        from src.schemas.domain import Customer
        c = Customer(
            id=1, name="A", email="a@x.com", plan="enterprise",
            created_at=datetime.now(timezone.utc),
        )
        assert c.plan is CustomerPlan.ENTERPRISE


# ---------------------------------------------------------------------------
# DependencyChain
# ---------------------------------------------------------------------------

class TestDependencyChain:
    def test_empty_lists_are_valid(self):
        dc = DependencyChain(source="orders")
        assert dc.downstream_pipelines == []
        assert dc.downstream_tables == []
        assert dc.downstream_dashboards == []
        assert dc.impacted_teams == []

    def test_populated_chain(self):
        dc = DependencyChain(
            source="orders",
            downstream_pipelines=["etl_billing_daily"],
            downstream_tables=["fact_revenue"],
            downstream_dashboards=["Revenue Overview"],
            impacted_teams=["team-billing", "team-analytics"],
        )
        assert "team-billing" in dc.impacted_teams


# ---------------------------------------------------------------------------
# HealthResponse
# ---------------------------------------------------------------------------

class TestHealthResponse:
    def test_accepts_arbitrary_service_names(self):
        hr = HealthResponse(
            status="degraded",
            services={"postgres": "healthy", "qdrant": "healthy", "weird-thing": "unhealthy"},
            uptime_seconds=12.5,
            version="1.0.0",
        )
        assert hr.services["weird-thing"] == "unhealthy"

    def test_status_defaults_to_healthy(self):
        hr = HealthResponse(services={}, uptime_seconds=0.0, version="1.0.0")
        assert hr.status == "healthy"


# ---------------------------------------------------------------------------
# Query-result models (smoke construction)
# ---------------------------------------------------------------------------

class TestQueryResults:
    def test_ledger_result(self):
        r = LedgerQueryResult(
            sql_query_executed="SELECT 1", summary="ok", row_count=1, data_points=[{"x": 1}]
        )
        assert r.data_points == [{"x": 1}]

    def test_memory_result_confidence_bounds(self):
        with pytest.raises(ValidationError):
            MemoryQueryResult(summary="x", confidence=1.1)

    def test_brain_result_with_dependency_chain(self):
        dc = DependencyChain(source="orders", downstream_pipelines=["p1"])
        r = BrainQueryResult(
            cypher_query_executed="MATCH (n) RETURN n",
            summary="ok",
            nodes_traversed=5,
            dependency_chain=dc,
        )
        assert r.dependency_chain.source == "orders"

    def test_synthesized_response_required_fields(self):
        r = SynthesizedResponse(
            answer="x",
            sources_consulted=["ledger"],
            confidence=0.5,
        )
        assert r.recommendation is None
        assert r.sub_questions == []
