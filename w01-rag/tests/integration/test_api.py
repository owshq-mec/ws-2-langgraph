"""Integration tests for the FastAPI surface.

Requires a running FastAPI at $API_BASE_URL (default http://localhost:8000),
e.g. via `make serve` or `docker compose up -d app`.
"""
from __future__ import annotations

import httpx
import pytest


@pytest.mark.integration
class TestAPI:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, api_base_url):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{api_base_url}/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] in {"healthy", "degraded", "unhealthy"}
            assert isinstance(data["services"], dict)
            assert "postgres" in data["services"]

    @pytest.mark.asyncio
    async def test_query_endpoint(self, api_base_url):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{api_base_url}/api/v1/query",
                json={"question": "How many customers do we have?"},
            )
            assert r.status_code == 200
            data = r.json()
            assert "answer" in data
            assert "sources_consulted" in data
            assert data["processing_time_ms"] > 0

    @pytest.mark.asyncio
    async def test_query_with_sources_filter(self, api_base_url):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{api_base_url}/api/v1/query",
                json={"question": "Who owns the billing pipeline?", "sources": ["brain"]},
            )
            assert r.status_code == 200
            data = r.json()
            assert all(s["source"] == "brain" for s in data["sources_consulted"])

    @pytest.mark.asyncio
    async def test_invalid_request(self, api_base_url):
        """Missing the required `question` field should yield 422."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{api_base_url}/api/v1/query", json={"wrong_field": "test"})
            assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_endpoint(self, api_base_url):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{api_base_url}/api/v1/ingest")
            # Either 202 (new job accepted) or 409 (one is already running).
            assert r.status_code in {202, 409}
