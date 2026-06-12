"""LedgerEngine — Text-to-SQL over PostgreSQL via LlamaIndex.

Wraps `NLSQLTableQueryEngine` with table descriptions tuned for our schema
and converts the LlamaIndex response into a `LedgerQueryResult`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from llama_index.core import SQLDatabase
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.llms.openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from src.engines.config import EngineConfig
from src.schemas.query import LedgerQueryResult

log = logging.getLogger(__name__)

__all__ = ["LedgerEngine"]

_INCLUDE_TABLES = ["customers", "orders", "products"]

_TABLE_DESCRIPTIONS: dict[str, str] = {
    "customers": (
        "Customer records with name, email, subscription plan "
        "(free/pro/enterprise), and company. Use for questions about customer "
        "counts, segments, plans."
    ),
    "orders": (
        "Order transactions with amount in BRL, quantity, status "
        "(pending/completed/failed/refunded), and timestamps. Use for revenue, "
        "sales volume, order status questions."
    ),
    "products": (
        "Product catalog with name, category, price, and SKU. Use for "
        "product-related questions."
    ),
}


def _coerce_rows(raw: Any) -> list[dict]:
    """Convert NLSQLTableQueryEngine's raw result into a list of dicts.

    LlamaIndex puts the executed query result in `response.metadata["result"]`
    as a list of tuples. SQLAlchemy column names live in `metadata["col_keys"]`
    when available. Fall back to positional keys.
    """
    if raw is None:
        return []
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return raw
    if not isinstance(raw, (list, tuple)):
        return []
    return [
        ({f"col_{i}": v for i, v in enumerate(row)} if isinstance(row, (list, tuple)) else {"value": row})
        for row in raw
    ]


class LedgerEngine:
    """Text-to-SQL engine over the PostgreSQL Ledger."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        try:
            self._sa_engine = create_engine(
                self.config.postgres_connection_string,
                pool_pre_ping=True,
                pool_recycle=300,
            )
            # Smoke-test connection so failures happen at construction, not first query.
            with self._sa_engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        except SQLAlchemyError as exc:
            raise RuntimeError(
                f"LedgerEngine: could not connect to PostgreSQL at "
                f"{self.config.postgres_host}:{self.config.postgres_port}: {exc}"
            ) from exc

        self._sql_database = SQLDatabase(
            self._sa_engine, include_tables=_INCLUDE_TABLES
        )
        self._llm = OpenAI(model=self.config.llm_model)
        self._engine = NLSQLTableQueryEngine(
            sql_database=self._sql_database,
            tables=_INCLUDE_TABLES,
            context_str_prefix=self._context_prefix(),
            llm=self._llm,
            synthesize_response=True,
        )

    @staticmethod
    def _context_prefix() -> str:
        lines = ["Table descriptions:"]
        for name, desc in _TABLE_DESCRIPTIONS.items():
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    async def _query_once(self, question: str) -> LedgerQueryResult:
        try:
            response = await self._engine.aquery(question)
        except Exception as exc:
            log.exception("Ledger query execution failed")
            return LedgerQueryResult(
                sql_query_executed="",
                summary=f"Query failed: {exc}",
                row_count=0,
                data_points=[],
            )

        meta = response.metadata or {}
        sql = str(meta.get("sql_query") or "").strip()
        rows = _coerce_rows(meta.get("result"))

        return LedgerQueryResult(
            sql_query_executed=sql,
            summary=str(response).strip(),
            row_count=len(rows),
            data_points=rows,
        )

    async def query(self, question: str) -> LedgerQueryResult:
        try:
            return await asyncio.wait_for(
                self._query_once(question),
                timeout=self.config.query_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return LedgerQueryResult(
                sql_query_executed="",
                summary=f"Query timed out after {self.config.query_timeout_seconds}s",
                row_count=0,
                data_points=[],
            )

    def close(self) -> None:
        try:
            self._sa_engine.dispose()
        except Exception:
            pass
