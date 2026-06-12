"""DataOps Knowledge Hub — continuous data generator.

Writes correlated synthetic data to PostgreSQL, MongoDB, and SeaweedFS on a
fixed interval. Sync drivers wrapped in asyncio.to_thread so the three writes
fan out concurrently per cycle.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import random
import secrets
import signal
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2
import psycopg2.extras
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from faker import Faker
from pymongo import MongoClient
from pymongo.errors import PyMongoError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("data-generator")

fake = Faker("pt_BR")
Faker.seed(None)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val  # type: ignore[return-value]


INTERVAL = int(env("GENERATOR_INTERVAL_SECONDS", "30"))

PG_DSN = {
    "host": env("POSTGRES_HOST", "postgres"),
    "port": int(env("POSTGRES_PORT", "5432")),
    "dbname": env("POSTGRES_DB", required=True),
    "user": env("POSTGRES_USER", required=True),
    "password": env("POSTGRES_PASSWORD", required=True),
}

MONGO_URI = f"mongodb://{env('MONGO_HOST', 'mongo')}:{env('MONGO_PORT', '27017')}"
MONGO_DB = env("MONGO_DB", required=True)

S3_ENDPOINT = f"http://{env('SEAWEEDFS_HOST', 'seaweedfs')}:{env('SEAWEEDFS_PORT', '8333')}"
S3_BUCKET = env("SEAWEEDFS_BUCKET", "dataops-lake")


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

PLANS = ["free"] * 6 + ["pro"] * 3 + ["enterprise"]  # 60/30/10

ORDER_STATUSES = (
    ["completed"] * 14 + ["pending"] * 3 + ["failed"] * 2 + ["refunded"]  # 70/15/10/5
)

PIPELINE_NAMES = [
    "etl_billing_daily",
    "etl_orders_hourly",
    "etl_customer_sync",
    "analytics_revenue_agg",
]

PIPELINE_STATUS = ["completed"] * 17 + ["failed"] * 2 + ["warning"]  # 85/10/5

PIPELINE_ERRORS = [
    "Connection timeout to source DB",
    "Schema mismatch on column revenue",
    "Out of memory during aggregation",
    "S3 PutObject failed: SlowDown",
    "Deadlock detected on orders.idx_status",
    "Watermark regressed; refusing to advance",
]

USER_ACTIONS = [
    "query_executed",
    "dashboard_viewed",
    "export_requested",
    "schema_browsed",
    "pipeline_triggered",
]

PRODUCT_CATEGORIES = ["Analytics", "Integration", "Storage", "Compute"]

PRODUCT_NAME_PARTS = {
    "Analytics":   ["Insight", "Pulse", "Lens", "Beacon", "Atlas"],
    "Integration": ["Bridge", "Conduit", "Relay", "Sync", "Pipe"],
    "Storage":     ["Vault", "Lake", "Shard", "Cache", "Archive"],
    "Compute":     ["Engine", "Forge", "Mesh", "Reactor", "Burst"],
}


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

async def with_retry(label: str, fn, *, attempts: int = 3, base_delay: float = 1.0):
    """Run a sync callable in a worker thread with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.to_thread(fn)
        except (psycopg2.Error, PyMongoError, BotoCoreError, ClientError, OSError) as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        label, attempt, attempts, exc, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

class PostgresWriter:
    def __init__(self) -> None:
        self.conn: psycopg2.extensions.connection | None = None

    def _connect(self) -> None:
        self.conn = psycopg2.connect(**PG_DSN)
        self.conn.autocommit = False

    async def connect(self) -> None:
        await with_retry("postgres.connect", self._connect)
        log.info("Connected to Postgres at %s:%s/%s",
                 PG_DSN["host"], PG_DSN["port"], PG_DSN["dbname"])

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def _bootstrap_products(self) -> None:
        """Seed an initial product catalogue so orders have FKs to reference."""
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM products")
            (count,) = cur.fetchone()
            if count > 0:
                return
            rows = [self._fake_product() for _ in range(12)]
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO products (name, category, price, sku, active) VALUES %s "
                "ON CONFLICT (sku) DO NOTHING",
                rows,
            )
            self.conn.commit()
            log.info("Bootstrap: seeded %d products", len(rows))

    async def bootstrap(self) -> None:
        await with_retry("postgres.bootstrap_products", self._bootstrap_products)

    @staticmethod
    def _fake_customer() -> tuple[str, str, str, str]:
        name = fake.name()
        email = f"{fake.user_name()}.{secrets.token_hex(2)}@{fake.free_email_domain()}"
        plan = random.choice(PLANS)
        company = fake.company()
        return name, email, plan, company

    @staticmethod
    def _fake_product() -> tuple[str, str, float, str, bool]:
        category = random.choice(PRODUCT_CATEGORIES)
        name = f"{random.choice(PRODUCT_NAME_PARTS[category])} {random.choice(['Pro', 'Cloud', 'X', 'One', 'Plus'])}"
        price = round(random.uniform(29.0, 999.0), 2)
        sku = f"SKU-{secrets.token_hex(4).upper()}"
        return name, category, price, sku, True

    def _write_cycle(self) -> dict[str, int]:
        """One synchronous Postgres cycle: customers, optional products, orders."""
        assert self.conn is not None
        counts = {"customers": 0, "products": 0, "orders": 0}
        try:
            with self.conn.cursor() as cur:
                # Customers
                customers = [self._fake_customer() for _ in range(random.randint(2, 5))]
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO customers (name, email, plan, company) VALUES %s "
                    "ON CONFLICT (email) DO NOTHING",
                    customers,
                )
                counts["customers"] = cur.rowcount

                # Products — every 5th cycle (probabilistic, no shared counter needed)
                if random.random() < 0.2:
                    products = [self._fake_product() for _ in range(random.randint(1, 3))]
                    psycopg2.extras.execute_values(
                        cur,
                        "INSERT INTO products (name, category, price, sku, active) VALUES %s "
                        "ON CONFLICT (sku) DO NOTHING",
                        products,
                    )
                    counts["products"] = cur.rowcount

                # Pools for FK targets
                cur.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 500")
                customer_ids = [r[0] for r in cur.fetchall()]
                cur.execute("SELECT id, price FROM products WHERE active = TRUE")
                product_pool = cur.fetchall()

                if customer_ids and product_pool:
                    orders = []
                    for _ in range(random.randint(5, 15)):
                        cid = random.choice(customer_ids)
                        pid, price = random.choice(product_pool)
                        qty = random.randint(1, 5)
                        amount = round(float(price) * qty, 2)
                        status = random.choice(ORDER_STATUSES)
                        orders.append((cid, pid, amount, qty, status))
                    psycopg2.extras.execute_values(
                        cur,
                        "INSERT INTO orders (customer_id, product_id, amount, quantity, status) VALUES %s",
                        orders,
                    )
                    counts["orders"] = cur.rowcount

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return counts

    async def write_cycle(self) -> dict[str, int]:
        return await with_retry("postgres.write_cycle", self._write_cycle)


# ---------------------------------------------------------------------------
# Mongo
# ---------------------------------------------------------------------------

class MongoWriter:
    def __init__(self) -> None:
        self.client: MongoClient | None = None
        self.db: Any = None

    def _connect(self) -> None:
        self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")
        self.db = self.client[MONGO_DB]

    async def connect(self) -> None:
        await with_retry("mongo.connect", self._connect)
        log.info("Connected to Mongo at %s/%s", MONGO_URI, MONGO_DB)

    def close(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    @staticmethod
    def _fake_event_log() -> dict[str, Any]:
        pipeline = random.choice(PIPELINE_NAMES)
        status = random.choice(PIPELINE_STATUS)
        is_daily = "daily" in pipeline or "agg" in pipeline
        duration = random.randint(30, 600) if is_daily else random.randint(10, 120)

        severity = {"completed": "info", "warning": "warning", "failed": "critical"}[status]
        records = 0 if status == "failed" else random.randint(1_000, 100_000)
        error = random.choice(PIPELINE_ERRORS) if status == "failed" else None

        return {
            "pipeline_name": pipeline,
            "status": status,
            "error_message": error,
            "severity": severity,
            "duration_seconds": duration,
            "records_processed": records,
            "timestamp": datetime.now(timezone.utc),
        }

    @staticmethod
    def _fake_user_activity() -> dict[str, Any]:
        action = random.choice(USER_ACTIONS)
        metadata: dict[str, Any]
        if action == "query_executed":
            metadata = {
                "table": random.choice(["customers", "orders", "products", "fact_revenue"]),
                "rows_returned": random.randint(1, 50_000),
                "execution_time_ms": random.randint(20, 8_000),
            }
        elif action == "dashboard_viewed":
            metadata = {
                "dashboard": random.choice(["Revenue Overview", "Customer Health", "Pipeline Monitor"]),
                "view_duration_seconds": random.randint(5, 600),
            }
        elif action == "export_requested":
            metadata = {
                "format": random.choice(["csv", "parquet", "xlsx"]),
                "row_count": random.randint(100, 100_000),
            }
        elif action == "schema_browsed":
            metadata = {"database": random.choice(["dataops", "warehouse"])}
        else:  # pipeline_triggered
            metadata = {"pipeline_name": random.choice(PIPELINE_NAMES)}

        return {
            "user_id": f"usr_{secrets.token_hex(4)}",
            "action": action,
            "metadata": metadata,
            "session_id": f"sess_{secrets.token_hex(4)}",
            "timestamp": datetime.now(timezone.utc),
        }

    def _write_cycle(self) -> dict[str, int]:
        events = [self._fake_event_log() for _ in range(random.randint(3, 8))]
        activity = [self._fake_user_activity() for _ in range(random.randint(5, 10))]
        self.db["event_logs"].insert_many(events)
        self.db["user_activity"].insert_many(activity)
        return {"event_logs": len(events), "user_activity": len(activity)}

    async def write_cycle(self) -> dict[str, int]:
        return await with_retry("mongo.write_cycle", self._write_cycle)


# ---------------------------------------------------------------------------
# SeaweedFS (S3)
# ---------------------------------------------------------------------------

class S3Writer:
    def __init__(self) -> None:
        self.client: Any = None

    def _connect(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id="any",
            aws_secret_access_key="any",
            region_name="us-east-1",
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        # Light readiness check — head_bucket; if missing, create it.
        try:
            self.client.head_bucket(Bucket=S3_BUCKET)
        except ClientError:
            self.client.create_bucket(Bucket=S3_BUCKET)

    async def connect(self) -> None:
        await with_retry("s3.connect", self._connect)
        log.info("Connected to SeaweedFS S3 at %s, bucket=%s", S3_ENDPOINT, S3_BUCKET)

    def _upload_daily_summary(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"reports/daily-summary-{today}.csv"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["metric", "value", "generated_at"])
        ts = datetime.now(timezone.utc).isoformat()
        w.writerow(["new_customers_today", random.randint(50, 500), ts])
        w.writerow(["orders_today", random.randint(500, 5000), ts])
        w.writerow(["gross_revenue_brl", round(random.uniform(10_000, 250_000), 2), ts])
        w.writerow(["failed_pipeline_runs", random.randint(0, 5), ts])
        w.writerow(["avg_pipeline_duration_s", random.randint(60, 300), ts])
        self.client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=buf.getvalue().encode("utf-8"),
            ContentType="text/csv",
        )
        return key

    async def maybe_upload_summary(self) -> str | None:
        """Every 10th cycle (10% probability per cycle)."""
        if random.random() >= 0.1:
            return None
        return await with_retry("s3.upload_summary", self._upload_daily_summary)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self) -> None:
        self.pg = PostgresWriter()
        self.mongo = MongoWriter()
        self.s3 = S3Writer()
        self.shutdown = asyncio.Event()

    async def setup(self) -> None:
        # Connect sequentially so we get clear log lines on which store is the laggard.
        await self.pg.connect()
        await self.mongo.connect()
        await self.s3.connect()
        await self.pg.bootstrap()

    async def one_cycle(self, cycle: int) -> None:
        pg_task = asyncio.create_task(self.pg.write_cycle())
        mongo_task = asyncio.create_task(self.mongo.write_cycle())
        s3_task = asyncio.create_task(self.s3.maybe_upload_summary())

        results = await asyncio.gather(pg_task, mongo_task, s3_task, return_exceptions=True)
        pg_res, mongo_res, s3_res = results

        if isinstance(pg_res, Exception):
            log.error("postgres cycle failed: %s", pg_res)
            pg_res = {}
        if isinstance(mongo_res, Exception):
            log.error("mongo cycle failed: %s", mongo_res)
            mongo_res = {}
        if isinstance(s3_res, Exception):
            log.error("s3 cycle failed: %s", s3_res)
            s3_res = None

        log.info(
            "cycle=%d pg=%s mongo=%s s3=%s",
            cycle,
            pg_res or "skipped",
            mongo_res or "skipped",
            s3_res or "no-upload",
        )

    async def run(self) -> None:
        await self.setup()
        log.info("Generator running. interval=%ds", INTERVAL)
        cycle = 0
        while not self.shutdown.is_set():
            cycle += 1
            try:
                await self.one_cycle(cycle)
            except Exception as exc:  # last-resort safety net
                log.exception("unhandled cycle error: %s", exc)
            try:
                await asyncio.wait_for(self.shutdown.wait(), timeout=INTERVAL)
            except asyncio.TimeoutError:
                pass
        log.info("Shutdown signal received — closing connections.")
        self.pg.close()
        self.mongo.close()
        log.info("Generator stopped after %d cycles.", cycle)

    def request_shutdown(self) -> None:
        if not self.shutdown.is_set():
            log.info("Shutdown requested.")
            self.shutdown.set()


async def amain() -> int:
    gen = Generator()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, gen.request_shutdown)
    await gen.run()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
