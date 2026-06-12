"""Domain models — business entities used for structured extraction and
as output schemas for LlamaIndex query engines."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CustomerPlan",
    "OrderStatus",
    "PipelineStatus",
    "Severity",
    "Customer",
    "Order",
    "PipelineEvent",
    "PipelineNode",
    "TableNode",
    "DependencyChain",
]


class CustomerPlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PipelineStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    WARNING = "warning"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Customer(BaseModel):
    """A customer entity from the Ledger (PostgreSQL)."""

    id: int = Field(description="Customer primary key")
    name: str = Field(description="Full customer name")
    email: str = Field(description="Customer email address")
    plan: CustomerPlan = Field(description="Subscription tier")
    company: Optional[str] = Field(default=None, description="Company name, if provided")
    created_at: datetime = Field(description="Account creation timestamp")


class Order(BaseModel):
    """An order entity from the Ledger (PostgreSQL)."""

    id: int = Field(description="Order primary key")
    customer_id: int = Field(description="FK to customers.id")
    product_id: int = Field(description="FK to products.id")
    amount: float = Field(description="Order total in BRL")
    quantity: int = Field(description="Number of units ordered")
    status: OrderStatus = Field(description="Order lifecycle status")
    created_at: datetime = Field(description="Order creation timestamp")


class PipelineEvent(BaseModel):
    """A pipeline execution event from Memory (MongoDB)."""

    pipeline_name: str = Field(description="Name of the pipeline that ran")
    status: PipelineStatus = Field(description="Outcome of the pipeline run")
    error_message: Optional[str] = Field(
        default=None, description="Error message when status is 'failed'; null otherwise"
    )
    severity: Severity = Field(description="Severity derived from status")
    duration_seconds: int = Field(description="Wall-clock duration of the pipeline run")
    records_processed: int = Field(description="Number of records processed in this run")
    timestamp: datetime = Field(description="When the event was recorded (UTC)")


class PipelineNode(BaseModel):
    """A pipeline node from the Brain (Neo4j)."""

    name: str = Field(description="Pipeline identifier, unique across the graph")
    schedule: str = Field(description="Cron schedule string")
    owner: str = Field(description="Owning team name")
    sla_minutes: int = Field(description="Maximum allowed latency in minutes")


class TableNode(BaseModel):
    """A table node from the Brain (Neo4j)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Table name, unique within the graph")
    schema_name: str = Field(
        alias="schema",
        description="Database schema the table belongs to",
    )
    database: str = Field(description="Database the table lives in")
    row_count: int = Field(description="Approximate row count last measured")


class DependencyChain(BaseModel):
    """Represents downstream dependencies of a pipeline or table."""

    source: str = Field(description="The originating pipeline or table name")
    downstream_pipelines: list[str] = Field(
        default_factory=list, description="Pipelines that consume from the source"
    )
    downstream_tables: list[str] = Field(
        default_factory=list, description="Tables written by pipelines downstream of the source"
    )
    downstream_dashboards: list[str] = Field(
        default_factory=list, description="Dashboards that rely on downstream data"
    )
    impacted_teams: list[str] = Field(
        default_factory=list, description="Teams that own anything in the dependency chain"
    )
