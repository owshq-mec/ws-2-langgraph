# Prompt 04 — Build Init Scripts

## Context

Docker Compose is running with all 5 services healthy. Now we need to initialize the databases with their schemas and seed data so the Data Generator (next prompt) has tables/collections/buckets to write into.

Reference `sketch/plan.md` section "Data Sources" for the exact schemas.

## Objective

Create initialization scripts that run once when the infrastructure first starts, establishing the data model for each store.

## Files to Create

### 1. `infra/scripts/init-databases.sql` (PostgreSQL)

Replace the existing stub with the full DDL:

```sql
-- DataOps Knowledge Hub — PostgreSQL Schema (Ledger)
-- This runs automatically on first container start

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    plan VARCHAR(20) NOT NULL DEFAULT 'free',  -- free, pro, enterprise
    company VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    sku VARCHAR(20) UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    amount DECIMAL(10,2) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, completed, failed, refunded
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common query patterns (Text-to-SQL will use these)
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
CREATE INDEX idx_customers_plan ON customers(plan);
CREATE INDEX idx_customers_company ON customers(company);
CREATE INDEX idx_products_category ON products(category);
```

### 2. `infra/scripts/init-neo4j.cypher` (Neo4j)

A Cypher script that creates constraints and seeds the graph with initial pipeline/table/dashboard topology:

```cypher
// Constraints (uniqueness)
CREATE CONSTRAINT pipeline_name IF NOT EXISTS FOR (p:Pipeline) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT table_name IF NOT EXISTS FOR (t:Table) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT dashboard_name IF NOT EXISTS FOR (d:Dashboard) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT team_name IF NOT EXISTS FOR (tm:Team) REQUIRE tm.name IS UNIQUE;

// Teams
CREATE (t1:Team {name: 'team-billing', slack_channel: '#billing-eng'});
CREATE (t2:Team {name: 'team-analytics', slack_channel: '#analytics'});
CREATE (t3:Team {name: 'team-platform', slack_channel: '#platform-eng'});

// Tables
CREATE (tb1:Table {name: 'customers', schema: 'public', database: 'dataops', row_count: 5000});
CREATE (tb2:Table {name: 'orders', schema: 'public', database: 'dataops', row_count: 50000});
CREATE (tb3:Table {name: 'products', schema: 'public', database: 'dataops', row_count: 200});
CREATE (tb4:Table {name: 'fact_revenue', schema: 'analytics', database: 'warehouse', row_count: 120000});
CREATE (tb5:Table {name: 'dim_customers', schema: 'analytics', database: 'warehouse', row_count: 5000});

// Pipelines
CREATE (p1:Pipeline {name: 'etl_billing_daily', schedule: '0 3 * * *', owner: 'team-billing', sla_minutes: 45});
CREATE (p2:Pipeline {name: 'etl_orders_hourly', schedule: '0 * * * *', owner: 'team-billing', sla_minutes: 15});
CREATE (p3:Pipeline {name: 'etl_customer_sync', schedule: '0 6 * * *', owner: 'team-platform', sla_minutes: 30});
CREATE (p4:Pipeline {name: 'analytics_revenue_agg', schedule: '0 5 * * *', owner: 'team-analytics', sla_minutes: 60});

// Dashboards
CREATE (d1:Dashboard {name: 'Revenue Overview', tool: 'Metabase', owner: 'team-analytics', refresh_frequency: 'hourly'});
CREATE (d2:Dashboard {name: 'Customer Health', tool: 'Metabase', owner: 'team-billing', refresh_frequency: 'daily'});
CREATE (d3:Dashboard {name: 'Pipeline Monitor', tool: 'Grafana', owner: 'team-platform', refresh_frequency: 'realtime'});

// Relationships — Pipeline reads/writes
MATCH (p:Pipeline {name: 'etl_billing_daily'}), (t:Table {name: 'orders'}) CREATE (p)-[:READS_FROM]->(t);
MATCH (p:Pipeline {name: 'etl_billing_daily'}), (t:Table {name: 'fact_revenue'}) CREATE (p)-[:WRITES_TO]->(t);
MATCH (p:Pipeline {name: 'etl_orders_hourly'}), (t:Table {name: 'orders'}) CREATE (p)-[:READS_FROM]->(t);
MATCH (p:Pipeline {name: 'etl_customer_sync'}), (t:Table {name: 'customers'}) CREATE (p)-[:READS_FROM]->(t);
MATCH (p:Pipeline {name: 'etl_customer_sync'}), (t:Table {name: 'dim_customers'}) CREATE (p)-[:WRITES_TO]->(t);
MATCH (p:Pipeline {name: 'analytics_revenue_agg'}), (t:Table {name: 'fact_revenue'}) CREATE (p)-[:READS_FROM]->(t);

// Relationships — Pipeline feeds pipeline
MATCH (p1:Pipeline {name: 'etl_billing_daily'}), (p2:Pipeline {name: 'analytics_revenue_agg'}) CREATE (p1)-[:FEEDS]->(p2);
MATCH (p1:Pipeline {name: 'etl_customer_sync'}), (p2:Pipeline {name: 'analytics_revenue_agg'}) CREATE (p1)-[:FEEDS]->(p2);

// Relationships — Table used by dashboard
MATCH (t:Table {name: 'fact_revenue'}), (d:Dashboard {name: 'Revenue Overview'}) CREATE (t)-[:USED_BY]->(d);
MATCH (t:Table {name: 'dim_customers'}), (d:Dashboard {name: 'Customer Health'}) CREATE (t)-[:USED_BY]->(d);
MATCH (t:Table {name: 'orders'}), (d:Dashboard {name: 'Pipeline Monitor'}) CREATE (t)-[:USED_BY]->(d);

// Relationships — Team owns
MATCH (tm:Team {name: 'team-billing'}), (p:Pipeline {name: 'etl_billing_daily'}) CREATE (tm)-[:OWNS]->(p);
MATCH (tm:Team {name: 'team-billing'}), (p:Pipeline {name: 'etl_orders_hourly'}) CREATE (tm)-[:OWNS]->(p);
MATCH (tm:Team {name: 'team-platform'}), (p:Pipeline {name: 'etl_customer_sync'}) CREATE (tm)-[:OWNS]->(p);
MATCH (tm:Team {name: 'team-analytics'}), (p:Pipeline {name: 'analytics_revenue_agg'}) CREATE (tm)-[:OWNS]->(p);
MATCH (tm:Team {name: 'team-billing'}), (t:Table {name: 'orders'}) CREATE (tm)-[:OWNS]->(t);
MATCH (tm:Team {name: 'team-platform'}), (t:Table {name: 'customers'}) CREATE (tm)-[:OWNS]->(t);
MATCH (tm:Team {name: 'team-analytics'}), (t:Table {name: 'fact_revenue'}) CREATE (tm)-[:OWNS]->(t);
```

### 3. `infra/scripts/init-seaweedfs.sh` (SeaweedFS)

A shell script that creates the S3 bucket and uploads initial documents:

```bash
#!/bin/bash
# Wait for SeaweedFS to be ready
until curl -sf http://seaweedfs:9333/cluster/status > /dev/null 2>&1; do
    echo "Waiting for SeaweedFS..."
    sleep 2
done

# Create bucket via S3 API
aws --endpoint-url http://seaweedfs:8333 s3 mb s3://dataops-lake 2>/dev/null || true

echo "SeaweedFS bucket 'dataops-lake' ready."
```

### 4. `infra/docs/` — Seed Documents for SeaweedFS

Create these markdown/text files that will be uploaded to SeaweedFS as the "unstructured knowledge" of the company:

#### `infra/docs/data-retention-policy.md`

A realistic data retention policy document (1-2 pages) covering:
- Retention periods per data classification (PII: 90 days, transactional: 7 years, logs: 30 days)
- Deletion procedures
- Compliance requirements (LGPD)
- Responsible teams

#### `infra/docs/sla-definitions.md`

SLA definitions for each pipeline:
- etl_billing_daily: 99.9% uptime, max 45 min latency
- etl_orders_hourly: 99.5% uptime, max 15 min latency
- etl_customer_sync: 99.0% uptime, max 30 min latency
- Escalation procedures per severity level

#### `infra/docs/incident-response-runbook.md`

Step-by-step incident response:
- Severity classification (P1-P4)
- Communication channels
- Rollback procedures
- Post-mortem template

#### `infra/docs/data-dictionary.csv`

```csv
table,column,type,description,owner,pii_flag,sla
customers,id,integer,Primary key auto-increment,team-platform,false,N/A
customers,name,varchar,Full customer name,team-platform,true,N/A
customers,email,varchar,Customer email address,team-platform,true,N/A
customers,plan,varchar,Subscription tier (free/pro/enterprise),team-billing,false,N/A
customers,company,varchar,Company name,team-platform,false,N/A
orders,id,integer,Primary key auto-increment,team-billing,false,N/A
orders,customer_id,integer,FK to customers table,team-billing,false,N/A
orders,amount,decimal,Order total in BRL,team-billing,false,N/A
orders,status,varchar,Order lifecycle status,team-billing,false,N/A
products,id,integer,Primary key auto-increment,team-platform,false,N/A
products,name,varchar,Product display name,team-platform,false,N/A
products,category,varchar,Product category,team-platform,false,N/A
products,price,decimal,Unit price in BRL,team-billing,false,N/A
fact_revenue,date,date,Aggregation date,team-analytics,false,daily
fact_revenue,total_revenue,decimal,Daily revenue sum,team-analytics,false,daily
```

### 5. `infra/scripts/seed-neo4j.sh`

A shell script that waits for Neo4j and runs the Cypher init:

```bash
#!/bin/bash
# Wait for Neo4j to be ready
until cypher-shell -u neo4j -p dataops123 "RETURN 1" > /dev/null 2>&1; do
    echo "Waiting for Neo4j..."
    sleep 3
done

# Run init script
cypher-shell -u neo4j -p dataops123 -f /scripts/init-neo4j.cypher
echo "Neo4j seeded successfully."
```

## Docker Compose Update

Add a one-shot `init` service to the `docker-compose.yml` that runs the SeaweedFS and Neo4j initialization scripts after those services are healthy. This service should:
- Depend on `neo4j` and `seaweedfs` (condition: service_healthy)
- Mount `./infra/scripts/` and `./infra/docs/`
- Run both init scripts sequentially
- Exit after completion (`restart: "no"`)

## Validation

After execution, verify:
- [ ] `docker compose up -d` → all services healthy + init service exits with code 0
- [ ] PostgreSQL: `docker compose exec postgres psql -U dataops -d dataops -c "\dt"` shows 3 tables
- [ ] Neo4j: Open `http://localhost:7474` → run `MATCH (n) RETURN count(n)` → should return nodes
- [ ] SeaweedFS: `aws --endpoint-url http://localhost:8333 s3 ls s3://dataops-lake/` shows bucket exists
- [ ] Seed documents exist in `infra/docs/` ready for upload
