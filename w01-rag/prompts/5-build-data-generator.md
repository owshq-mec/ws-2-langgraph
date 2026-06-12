# Prompt 05 — Build Data Generator

## Context

All infrastructure is running (Postgres, MongoDB, Qdrant, Neo4j, SeaweedFS) with schemas initialized and seed data in place. Now we need a **continuous data generator** that simulates a live enterprise operation — new customers signing up, orders being placed, pipeline events firing, and user activity flowing.

This service runs as a Docker container alongside the infra, producing realistic data every cycle.

## Objective

Create a Data Generator service that continuously populates PostgreSQL, MongoDB, and SeaweedFS with realistic, correlated data using Faker.

## Files to Create

### 1. `generator/main.py`

A Python script that runs in an infinite loop, generating data every 30 seconds (configurable via env var `GENERATOR_INTERVAL_SECONDS`).

#### Requirements:

**PostgreSQL (Ledger) — Inserts:**
- Generate 2-5 new customers per cycle (realistic Brazilian names, company names, emails, random plan distribution: 60% free, 30% pro, 10% enterprise)
- Generate 5-15 new orders per cycle (linked to existing customers and products, realistic amounts based on product price * quantity, status distribution: 70% completed, 15% pending, 10% failed, 5% refunded)
- Generate 1-3 new products occasionally (every 5th cycle), with realistic tech/data product names, categories like "Analytics", "Integration", "Storage", "Compute", prices between R$29-R$999

**MongoDB (Events) — Inserts:**
- Generate 3-8 `event_logs` per cycle simulating pipeline runs:
  - `pipeline_name`: randomly pick from the 4 pipelines defined in Neo4j (etl_billing_daily, etl_orders_hourly, etl_customer_sync, analytics_revenue_agg)
  - `status`: 85% "completed", 10% "failed", 5% "warning"
  - `error_message`: null for completed, realistic error messages for failed (e.g., "Connection timeout to source DB", "Schema mismatch on column revenue", "Out of memory during aggregation")
  - `severity`: derived from status (completed→info, warning→warning, failed→critical)
  - `duration_seconds`: realistic range (30-600 for daily, 10-120 for hourly)
  - `records_processed`: realistic numbers (0 for failed, 1000-100000 for completed)
  - `timestamp`: current time

- Generate 5-10 `user_activity` per cycle:
  - `user_id`: format `usr_<random_hex_8>`
  - `action`: one of "query_executed", "dashboard_viewed", "export_requested", "schema_browsed", "pipeline_triggered"
  - `metadata`: varies by action type (e.g., query_executed includes table name, rows_returned, execution_time_ms)
  - `session_id`: format `sess_<random_hex_8>`
  - `timestamp`: current time

**SeaweedFS (Data Lake) — Occasional uploads (every 10th cycle):**
- Generate a small CSV report file (e.g., `reports/daily-summary-YYYY-MM-DD.csv`) with aggregated metrics
- Upload to `s3://dataops-lake/reports/`

#### Code Quality:
- Use `asyncio` for concurrent writes to all 3 stores
- Graceful shutdown on SIGTERM/SIGINT
- Logging with structured output (timestamp, store, records_generated)
- Connection retry logic (if a store is temporarily unavailable, retry 3 times with backoff)
- Use environment variables for all connection strings (from `.env`)

### 2. `generator/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "main.py"]
```

### 3. `generator/requirements.txt`

```
faker>=30.0
psycopg2-binary>=2.9
pymongo>=4.8
boto3>=1.35
python-dotenv>=1.0
```

### 4. Update `docker-compose.yml`

Add the `data-generator` service:

```yaml
  data-generator:
    build:
      context: ./generator
      dockerfile: Dockerfile
    env_file: .env
    environment:
      - GENERATOR_INTERVAL_SECONDS=30
    depends_on:
      postgres:
        condition: service_healthy
      mongo:
        condition: service_healthy
      seaweedfs:
        condition: service_healthy
    networks:
      - dataops-network
    restart: unless-stopped
```

## Validation

After execution, verify:
- [ ] `docker compose up -d data-generator` starts without errors
- [ ] `docker compose logs data-generator` shows generation cycles every 30s
- [ ] PostgreSQL: `SELECT count(*) FROM customers;` increases over time
- [ ] PostgreSQL: `SELECT count(*) FROM orders;` increases over time
- [ ] MongoDB: `db.event_logs.countDocuments()` increases over time
- [ ] MongoDB: `db.user_activity.countDocuments()` increases over time
- [ ] SeaweedFS: new files appear in `s3://dataops-lake/reports/` after ~5 minutes
- [ ] Graceful shutdown: `docker compose stop data-generator` exits cleanly (no orphan connections)
