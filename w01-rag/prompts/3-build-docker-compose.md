# Prompt 03 — Build Docker Compose

## Context

The project scaffold is in place (directories, pyproject.toml, Makefile, .env.example). Now we need the infrastructure — all data stores running locally via Docker Compose so we can start populating and querying them.

Reference the architecture in `sketch/plan.md` for the full list of services.

## Objective

Create a `docker-compose.yml` at the project root that brings up the entire infrastructure stack with proper health checks, volumes, networking, and dependency ordering.

## Services Required

### 1. PostgreSQL (Ledger)

| Property | Value |
|----------|-------|
| Image | `postgres:16-alpine` |
| Port | `5432:5432` |
| Volume | `pg_data:/var/lib/postgresql/data` |
| Environment | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` from `.env` |
| Health check | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` |
| Init script | Mount `./infra/scripts/init-databases.sql` to `/docker-entrypoint-initdb.d/` |

### 2. MongoDB (Events/Logs)

| Property | Value |
|----------|-------|
| Image | `mongo:7` |
| Port | `27017:27017` |
| Volume | `mongo_data:/data/db` |
| Environment | No auth for dev (simplicity) |
| Health check | `mongosh --eval "db.adminCommand('ping')"` |

### 3. Qdrant (Memory — Vector DB)

| Property | Value |
|----------|-------|
| Image | `qdrant/qdrant:latest` |
| Port | `6333:6333` (HTTP), `6334:6334` (gRPC) |
| Volume | `qdrant_data:/qdrant/storage` |
| Health check | `wget --no-verbose --tries=1 --spider http://localhost:6333/healthz` |

### 4. Neo4j (Brain — Graph DB)

| Property | Value |
|----------|-------|
| Image | `neo4j:5-community` |
| Port | `7474:7474` (UI), `7687:7687` (Bolt) |
| Volume | `neo4j_data:/data` |
| Environment | `NEO4J_AUTH=neo4j/dataops123`, `NEO4J_PLUGINS=["apoc"]` |
| Health check | `cypher-shell -u neo4j -p dataops123 "RETURN 1"` |

### 5. SeaweedFS (Data Lake — S3-compatible)

| Property | Value |
|----------|-------|
| Image | `chrislusf/seaweedfs:latest` |
| Command | `server -s3 -dir=/data` |
| Port | `8333:8333` (S3 API), `9333:9333` (Master) |
| Volume | `seaweedfs_data:/data` |
| Health check | `wget --no-verbose --tries=1 --spider http://localhost:9333/cluster/status` |

## Additional Requirements

### Networking
- Create a custom network `dataops-network` (bridge driver)
- All services on the same network

### Volumes
- All named volumes declared at the bottom of the file
- Data persists across restarts

### Environment Variables
- Use `env_file: .env` for services that need credentials
- PostgreSQL and Neo4j credentials come from `.env`

### Dependency Order
- No service depends on another at this stage (the data generator will depend on them later)
- Health checks ensure services are ready before external connections

## Output

A single file: `docker-compose.yml` at the project root.

## Validation

After creation, verify:
- [ ] `docker compose config` passes without errors
- [ ] `docker compose up -d` starts all 5 services
- [ ] `docker compose ps` shows all services as "healthy" within 60 seconds
- [ ] PostgreSQL accepts connections: `docker compose exec postgres pg_isready`
- [ ] MongoDB accepts connections: `docker compose exec mongo mongosh --eval "db.getName()"`
- [ ] Qdrant responds: `curl http://localhost:6333/healthz`
- [ ] Neo4j responds: `curl http://localhost:7474`
- [ ] SeaweedFS responds: `curl http://localhost:9333/cluster/status`
