# Prompt 14 — Production Deployment (DigitalOcean)

## Context

The system is fully built and tested locally:
- Docker Compose with all services running and healthy
- Data Generator populating continuously
- Ingestion Pipeline indexing into Qdrant
- FastAPI serving at port 8000
- MCP Server exposing tools
- 45/45 tests passing

Now we deploy to **production** on a DigitalOcean Droplet so the system runs 24/7 with a public IP.

## Objective

Deploy the DataOps Knowledge Hub to a DigitalOcean Droplet using `doctl` CLI. The result:
1. A public IP where the API is accessible (`http://<DROPLET_IP>:8000`)
2. MCP server pointing to production URL (any Claude Code instance can consume it)
3. Data generator running continuously — always fresh data
4. System survives reboots (`restart: always`)

## Files to Delete

### `railway.toml`

Delete this file — we're using DigitalOcean, not Railway.

```bash
rm -f railway.toml
```

## Files to Create/Update

### 1. `scripts/deploy-digitalocean.sh`

Full automated deployment via `doctl` CLI:

```bash
#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# DataOps Knowledge Hub — DigitalOcean Production Deployment
# ═══════════════════════════════════════════════════════════════

DROPLET_NAME="dataops-knowledge-hub"
REGION="nyc1"
SIZE="s-2vcpu-4gb"          # 2 vCPU, 4GB RAM — enough for all containers
IMAGE="docker-20-04"        # Pre-installed Docker image
SSH_KEY_NAME=""             # Will be auto-detected

echo "🚀 DataOps Knowledge Hub — DigitalOcean Deployment"
echo "==================================================="

# ─── Prerequisites ───────────────────────────────────────────
echo ""
echo "📋 Checking prerequisites..."

command -v doctl >/dev/null 2>&1 || { echo "❌ doctl not found. Install: https://docs.digitalocean.com/reference/doctl/how-to/install/"; exit 1; }
doctl account get >/dev/null 2>&1 || { echo "❌ doctl not authenticated. Run: doctl auth init"; exit 1; }

if [ ! -f .env.production ]; then
    echo "❌ .env.production not found."
    echo "   Copy from .env.production.example and fill in real values:"
    echo "   cp .env.production.example .env.production"
    exit 1
fi

echo "✅ doctl authenticated"
echo "✅ .env.production exists"

# ─── Get SSH Key ─────────────────────────────────────────────
echo ""
echo "🔑 Detecting SSH key..."

SSH_KEY_ID=$(doctl compute ssh-key list --format ID --no-header | head -1)
if [ -z "$SSH_KEY_ID" ]; then
    echo "❌ No SSH keys found in your DO account."
    echo "   Add one: doctl compute ssh-key create my-key --public-key-file ~/.ssh/id_rsa.pub"
    exit 1
fi
echo "✅ Using SSH key ID: $SSH_KEY_ID"

# ─── Check if Droplet Already Exists ────────────────────────
echo ""
echo "🔍 Checking for existing droplet..."

EXISTING_IP=$(doctl compute droplet list --format Name,PublicIPv4 --no-header | grep "^${DROPLET_NAME}" | awk '{print $2}' || true)

if [ -n "$EXISTING_IP" ]; then
    echo "⚠️  Droplet '${DROPLET_NAME}' already exists at ${EXISTING_IP}"
    echo "   Updating deployment on existing droplet..."
    DROPLET_IP="$EXISTING_IP"
else
    # ─── Create Droplet ──────────────────────────────────────
    echo "🏗️  Creating Droplet: ${DROPLET_NAME} (${SIZE} in ${REGION})..."

    doctl compute droplet create "$DROPLET_NAME" \
        --region "$REGION" \
        --size "$SIZE" \
        --image "$IMAGE" \
        --ssh-keys "$SSH_KEY_ID" \
        --tag-names "dataops,production" \
        --wait

    echo "⏳ Waiting for Droplet to be ready..."
    sleep 10

    DROPLET_IP=$(doctl compute droplet list --format Name,PublicIPv4 --no-header | grep "^${DROPLET_NAME}" | awk '{print $2}')
    echo "✅ Droplet created: ${DROPLET_IP}"

    # Wait for SSH to be available
    echo "⏳ Waiting for SSH..."
    for i in {1..30}; do
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$DROPLET_IP" "echo ok" >/dev/null 2>&1; then
            break
        fi
        sleep 5
    done
    echo "✅ SSH ready"
fi

# ─── Deploy to Droplet ───────────────────────────────────────
echo ""
echo "📦 Deploying to ${DROPLET_IP}..."

# Copy .env.production to the droplet
scp -o StrictHostKeyChecking=no .env.production root@"$DROPLET_IP":/tmp/.env.production

# Run deployment commands on the droplet
ssh -o StrictHostKeyChecking=no root@"$DROPLET_IP" bash -s <<'REMOTE_SCRIPT'
set -euo pipefail

APP_DIR="/opt/dataops-knowledge-hub"
REPO_URL="https://github.com/owshq-manus-ai/dataops-knowledge-hub.git"

echo "── Installing docker-compose plugin if needed..."
if ! docker compose version >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
fi

echo "── Cloning/updating repository..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

echo "── Setting up environment..."
cp /tmp/.env.production .env
rm -f /tmp/.env.production

echo "── Pulling images..."
docker compose -f docker-compose.production.yml pull

echo "── Building application..."
docker compose -f docker-compose.production.yml build

echo "── Starting services..."
docker compose -f docker-compose.production.yml up -d

echo "── Waiting for services to be healthy (60s)..."
sleep 60

echo "── Running init scripts..."
docker compose -f docker-compose.production.yml up init-neo4j --wait 2>/dev/null || true
docker compose -f docker-compose.production.yml up init-seaweedfs --wait 2>/dev/null || true

echo "── Waiting for data generator to populate (30s)..."
sleep 30

echo "── Running ingestion pipeline..."
docker compose -f docker-compose.production.yml exec -T app python -m src.ingestion.run || echo "⚠️ Ingestion may need retry"

echo "── Checking health..."
curl -sf http://localhost:8000/health || echo "⚠️ Health check pending"

echo ""
echo "✅ Deployment complete on remote!"
REMOTE_SCRIPT

# ─── Verify from local ──────────────────────────────────────
echo ""
echo "🏥 Verifying from local machine..."
sleep 5

if curl -sf "http://${DROPLET_IP}:8000/health" > /dev/null 2>&1; then
    echo "✅ API is healthy!"
    curl -s "http://${DROPLET_IP}:8000/health" | python3 -m json.tool
else
    echo "⚠️  API not responding yet. May need a minute. Try:"
    echo "   curl http://${DROPLET_IP}:8000/health"
fi

# ─── Summary ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "   🌐 API:     http://${DROPLET_IP}:8000"
echo "   📖 Docs:    http://${DROPLET_IP}:8000/docs"
echo "   🏥 Health:  http://${DROPLET_IP}:8000/health"
echo ""
echo "   🔧 SSH:     ssh root@${DROPLET_IP}"
echo "   📊 Logs:    ssh root@${DROPLET_IP} 'cd /opt/dataops-knowledge-hub && docker compose -f docker-compose.production.yml logs -f app'"
echo ""
echo "   🤖 MCP Config (update mcp-config.json):"
echo "   API_BASE_URL=http://${DROPLET_IP}:8000"
echo ""
echo "═══════════════════════════════════════════════════════════"
```

### 2. `scripts/destroy-digitalocean.sh`

Teardown script (for cleanup after workshop):

```bash
#!/bin/bash
set -euo pipefail

DROPLET_NAME="dataops-knowledge-hub"

echo "⚠️  This will DESTROY the Droplet '${DROPLET_NAME}' and all its data."
read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

DROPLET_ID=$(doctl compute droplet list --format Name,ID --no-header | grep "^${DROPLET_NAME}" | awk '{print $2}')

if [ -z "$DROPLET_ID" ]; then
    echo "❌ Droplet '${DROPLET_NAME}' not found."
    exit 1
fi

doctl compute droplet delete "$DROPLET_ID" --force
echo "✅ Droplet destroyed."
```

### 3. Update `scripts/deploy.sh`

Replace the existing Railway-oriented deploy script with a generic one that works on any machine with Docker:

```bash
#!/bin/bash
set -euo pipefail

echo "🚀 DataOps Knowledge Hub — Local Production Deploy"
echo "==================================================="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "❌ Docker Compose not found"; exit 1; }

# Check .env exists
if [ ! -f .env ]; then
    if [ -f .env.production ]; then
        cp .env.production .env
        echo "📋 Copied .env.production → .env"
    else
        echo "❌ No .env file found. Copy from .env.production.example and fill in values."
        exit 1
    fi
fi

# Validate no placeholder passwords
if grep -q "STRONG_PASSWORD_HERE" .env; then
    echo "❌ .env still has placeholder passwords. Replace <STRONG_PASSWORD_HERE> with real values."
    exit 1
fi

# Pull latest images
echo "📦 Pulling latest images..."
docker compose -f docker-compose.production.yml pull

# Build app + generator
echo "🔨 Building application..."
docker compose -f docker-compose.production.yml build

# Start everything
echo "🏗️  Starting services..."
docker compose -f docker-compose.production.yml up -d

# Wait for health
echo "⏳ Waiting for services to be healthy..."
for i in {1..24}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ API is healthy!"
        break
    fi
    echo "   Waiting... ($((i*5))s)"
    sleep 5
done

# Run init scripts (idempotent)
echo "🌱 Running init scripts..."
docker compose -f docker-compose.production.yml up init-neo4j --wait 2>/dev/null || true
docker compose -f docker-compose.production.yml up init-seaweedfs --wait 2>/dev/null || true

# Wait for data generator
echo "📊 Waiting for data generator (30s)..."
sleep 30

# Run ingestion
echo "🧠 Running ingestion pipeline..."
docker compose -f docker-compose.production.yml exec -T app python -m src.ingestion.run

# Final health check
echo ""
echo "🏥 Final health check:"
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo "✅ Deployment complete!"
echo "   API:    http://localhost:8000"
echo "   Docs:   http://localhost:8000/docs"
echo "   Health: http://localhost:8000/health"
```

### 4. Update `Makefile`

Replace Railway targets with DigitalOcean targets:

```makefile
# ═══ Production (DigitalOcean) ═══
deploy-do:
	bash scripts/deploy-digitalocean.sh

destroy-do:
	bash scripts/destroy-digitalocean.sh

deploy-local:
	bash scripts/deploy.sh

prod-up:
	docker compose -f docker-compose.production.yml up -d

prod-down:
	docker compose -f docker-compose.production.yml down

prod-logs:
	docker compose -f docker-compose.production.yml logs -f app

prod-restart:
	docker compose -f docker-compose.production.yml restart app

prod-status:
	docker compose -f docker-compose.production.yml ps

prod-ingest:
	bash scripts/seed-and-ingest.sh
```

### 5. Update `mcp-config.json`

Update the production example to use DigitalOcean IP:

```json
{
  "mcpServers": {
    "dataops-knowledge-hub-local": {
      "command": "python",
      "args": ["-m", "src.mcp.run"],
      "cwd": "<PROJECT_DIR>",
      "env": {
        "API_BASE_URL": "http://localhost:8000"
      }
    },
    "dataops-knowledge-hub-production": {
      "command": "python",
      "args": ["-m", "src.mcp.run"],
      "cwd": "<PROJECT_DIR>",
      "env": {
        "API_BASE_URL": "http://<DROPLET_IP>:8000"
      }
    }
  }
}
```

### 6. Update `.env.production.example`

Add a note about DigitalOcean:

```env
# ═══════════════════════════════════════════════════════════
# DataOps Knowledge Hub — Production Environment
# ═══════════════════════════════════════════════════════════
# Copy this file to .env.production and fill in real values.
# For DigitalOcean deployment: scripts/deploy-digitalocean.sh
# ═══════════════════════════════════════════════════════════

# OpenAI
OPENAI_API_KEY=sk-...

# PostgreSQL
POSTGRES_DB=dataops
POSTGRES_USER=dataops
POSTGRES_PASSWORD=<STRONG_PASSWORD_HERE>

# MongoDB
MONGO_DB=dataops

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=<STRONG_PASSWORD_HERE>

# App
APP_PORT=8000
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small
```

### 7. Update `README.md`

Update the deployment section to reference DigitalOcean instead of Railway:

**Production Deployment section should include:**
- Prerequisites: `doctl` installed and authenticated, SSH key in DO account
- Quick deploy: `make deploy-do`
- Manual steps if needed
- How to check logs: `ssh root@<IP> 'cd /opt/dataops-knowledge-hub && docker compose -f docker-compose.production.yml logs -f app'`
- How to destroy: `make destroy-do`
- Cost: ~$24/month (s-2vcpu-4gb)
- MCP config with production IP

## Validation

- [ ] `railway.toml` deleted
- [ ] `scripts/deploy-digitalocean.sh` is executable and passes `bash -n` syntax check
- [ ] `scripts/destroy-digitalocean.sh` is executable and passes `bash -n` syntax check
- [ ] `scripts/deploy.sh` updated and passes `bash -n` syntax check
- [ ] `docker compose -f docker-compose.production.yml config` validates
- [ ] `Makefile` has all new targets (deploy-do, destroy-do, deploy-local, prod-*)
- [ ] `mcp-config.json` has both local and production entries
- [ ] `README.md` updated with DigitalOcean instructions
- [ ] No remaining references to Railway in any file
