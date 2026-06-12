#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# bootstrap-w01.sh — sobe o "cérebro" do W01 (DataOps Knowledge Hub) do zero.
#
# Um comando: garante o runtime (OrbStack/Docker), sobe o data plane do W01,
# espera tudo ficar healthy, confirma que há dados VIVOS fluindo, e imprime
# um banner com portas + próximos passos. Idempotente: rodar 2x não quebra.
#
# Uso:
#   bash scripts/bootstrap-w01.sh            # sobe o data plane (caminho do agente)
#   bash scripts/bootstrap-w01.sh --with-api # também sobe a API /query (precisa OPENAI_API_KEY)
#   bash scripts/bootstrap-w01.sh --down     # derruba tudo (mantém os volumes/dados)
#   bash scripts/bootstrap-w01.sh --nuke     # derruba E apaga os volumes (reset total)
#
# Por que data plane != API: o Quality Guardian (W02) lê o Ledger via SQL DIRETO
# no Postgres — NÃO precisa de OpenAI. A API /query (RAG semântico) é a única peça
# que exige OPENAI_API_KEY, então fica OPCIONAL. Assim o setup nunca trava ao vivo
# por falta de chave.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ---- localização: este script vive em workshop/w02-langgraph/scripts/ ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W01_DIR="$(cd "${SCRIPT_DIR}/../w01-rag" && pwd)"

# ---- serviços do data plane (o que o agente realmente consome) ----
# Ordem não importa pro compose (ele resolve depends_on), mas listamos explícito
# pra subir SÓ o data plane por padrão (sem o 'app' que precisa de OpenAI).
DATA_SERVICES=(postgres mongo qdrant neo4j seaweedfs)
INIT_SERVICES=(init-neo4j init-seaweedfs)
GEN_SERVICE=(data-generator)

PG_CONTAINER="dataops-postgres"
PG_USER="dataops"
PG_DB="dataops"
HOST_PG_PORT="5442"   # remapeado p/ não conflitar com outros Postgres locais

# ---- cores (terminal turbinado, sem dependência externa) ----
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'
  YLW=$'\033[33m'; BLU=$'\033[34m'; CYN=$'\033[36m'; RST=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GRN=""; YLW=""; BLU=""; CYN=""; RST=""
fi

say()  { printf "%s\n" "$*"; }
step() { printf "\n${BOLD}${BLU}▸ %s${RST}\n" "$*"; }
ok()   { printf "  ${GRN}✓${RST} %s\n" "$*"; }
warn() { printf "  ${YLW}!${RST} %s\n" "$*"; }
die()  { printf "\n${RED}✗ %s${RST}\n" "$*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# 0. parse de argumentos
# ─────────────────────────────────────────────────────────────────────────────
WITH_API=0
case "${1:-}" in
  --with-api) WITH_API=1 ;;
  --down)
    step "Derrubando o W01 (volumes preservados)…"
    ( cd "$W01_DIR" && docker compose down )
    ok "W01 parado. Dados preservados (volumes intactos)."
    exit 0 ;;
  --nuke)
    step "RESET TOTAL: derrubando o W01 e APAGANDO os volumes…"
    ( cd "$W01_DIR" && docker compose down -v )
    ok "W01 zerado. Próximo 'up' recria o schema e repopula do zero."
    exit 0 ;;
  "" ) : ;;
  * ) die "Argumento desconhecido: $1  (use: --with-api | --down | --nuke)" ;;
esac

printf "${BOLD}${CYN}"
cat <<'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║   W01 · DataOps Knowledge Hub — bootstrap (cérebro do W02)        ║
╚══════════════════════════════════════════════════════════════════╝
BANNER
printf "${RST}"

# ─────────────────────────────────────────────────────────────────────────────
# 1. runtime: garantir OrbStack (ou Docker Desktop) de pé
# ─────────────────────────────────────────────────────────────────────────────
step "1/6 · Runtime de containers"
command -v docker >/dev/null 2>&1 || die "docker não encontrado no PATH. Instale o OrbStack ou o Docker Desktop."

if ! docker info >/dev/null 2>&1; then
  warn "Docker daemon não está respondendo — tentando iniciar o runtime…"
  if command -v orb >/dev/null 2>&1; then
    orb start >/dev/null 2>&1 || true
  elif [[ "$(uname)" == "Darwin" ]]; then
    open -ga "Docker" 2>/dev/null || true
  fi
  # espera o daemon ficar disponível (até ~60s)
  for i in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    sleep 2
    [[ $i -eq 30 ]] && die "Daemon não respondeu em 60s. Abra o OrbStack/Docker Desktop manualmente e rode de novo."
  done
fi
ok "Runtime ativo ($(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'))."

# ─────────────────────────────────────────────────────────────────────────────
# 2. .env: garantir que existe (o compose depende dele)
# ─────────────────────────────────────────────────────────────────────────────
step "2/6 · Arquivo .env do W01"
if [[ ! -f "${W01_DIR}/.env" ]]; then
  [[ -f "${W01_DIR}/.env.example" ]] || die ".env e .env.example ausentes em ${W01_DIR}."
  cp "${W01_DIR}/.env.example" "${W01_DIR}/.env"
  ok "Criado ${W01_DIR}/.env a partir do .env.example."
else
  ok ".env já existe."
fi

# detecta chave OpenAI sem imprimir o valor (só pra decidir se sobe a API)
HAS_OPENAI=0
if grep -Eq '^OPENAI_API_KEY=sk-' "${W01_DIR}/.env" 2>/dev/null; then HAS_OPENAI=1; fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. subir o data plane (+ inits + generator)
# ─────────────────────────────────────────────────────────────────────────────
step "3/6 · Subindo o data plane (stores + inits + generator)"
say "  ${DIM}stores:${RST} ${DATA_SERVICES[*]}"
(
  cd "$W01_DIR"
  docker compose up -d "${DATA_SERVICES[@]}"
  # os jobs de init rodam uma vez e saem (restart: no) — tolere falha idempotente
  docker compose up -d "${INIT_SERVICES[@]}" 2>/dev/null || true
  docker compose up -d --build "${GEN_SERVICE[@]}"
)
ok "Containers solicitados."

# ─────────────────────────────────────────────────────────────────────────────
# 4. esperar saúde dos stores principais (Postgres é o crítico p/ o agente)
# ─────────────────────────────────────────────────────────────────────────────
step "4/6 · Aguardando saúde dos containers"
wait_healthy() {
  local name="$1" max="${2:-40}" i
  for i in $(seq 1 "$max"); do
    local st
    st="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || echo missing)"
    case "$st" in
      healthy|running) printf "  ${GRN}✓${RST} %-22s %s\n" "$name" "$st"; return 0 ;;
      missing)         sleep 2 ;;
      *)               printf "  ${DIM}… %-22s %s (%d/%d)${RST}\r" "$name" "$st" "$i" "$max"; sleep 2 ;;
    esac
  done
  printf "\n"; warn "$name não ficou saudável a tempo (siga mesmo assim; verifique com 'docker compose ps')."
  return 1
}
wait_healthy "$PG_CONTAINER" 40 || die "Postgres (Ledger) é obrigatório p/ o agente — não ficou pronto."
wait_healthy "dataops-qdrant" 30 || true
wait_healthy "dataops-neo4j"  40 || true
wait_healthy "dataops-mongo"  30 || true
wait_healthy "dataops-seaweedfs" 30 || true

# ─────────────────────────────────────────────────────────────────────────────
# 5. verificar DADOS VIVOS (o "momento aha" do setup)
# ─────────────────────────────────────────────────────────────────────────────
step "5/6 · Verificando dados vivos no Ledger"
pg_count() {
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc \
    "SELECT count(*) FROM ${1};" 2>/dev/null | tr -d '[:space:]'
}
# 1ª leitura
c1="$(pg_count customers || echo 0)"; c1="${c1:-0}"
if [[ "$c1" -eq 0 ]]; then
  warn "0 customers ainda — o generator escreve a cada 30s. Aguardando 1 ciclo…"
  sleep 32
  c1="$(pg_count customers || echo 0)"; c1="${c1:-0}"
fi
[[ "$c1" -gt 0 ]] || die "Sem dados após o ciclo do generator. Veja 'docker compose logs data-generator'."
ok "customers=${c1} · products=$(pg_count products) · orders=$(pg_count orders)"

# prova de que está VIVO: espera um ciclo e mostra o delta
say "  ${DIM}confirmando fluxo contínuo (1 ciclo do generator ~30s)…${RST}"
sleep 32
c2="$(pg_count customers || echo "$c1")"; c2="${c2:-$c1}"
if [[ "$c2" -gt "$c1" ]]; then
  ok "Fluxo confirmado: customers ${c1} → ${c2} (+$((c2 - c1)) no último ciclo). ${GRN}Dados estão vivos.${RST}"
else
  warn "Sem crescimento neste ciclo (normal: inserts têm jitter). Generator está up; rode de novo se quiser ver o delta."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. (opcional) subir a API /query — só com OpenAI key
# ─────────────────────────────────────────────────────────────────────────────
step "6/6 · API /query (RAG semântico) — opcional"
if [[ "$WITH_API" -eq 1 ]]; then
  if [[ "$HAS_OPENAI" -eq 1 ]]; then
    ( cd "$W01_DIR" && docker compose up -d --build app )
    wait_healthy "dataops-app" 40 || true
    ok "API /query subindo em http://localhost:8000 (precisa de embeddings — 1ª query é mais lenta)."
  else
    warn "--with-api pedido, mas OPENAI_API_KEY não encontrada no .env. Pulei a API."
    warn "Adicione OPENAI_API_KEY=sk-... em ${W01_DIR}/.env e rode com --with-api."
  fi
else
  if [[ "$HAS_OPENAI" -eq 1 ]]; then
    say "  ${DIM}OpenAI key detectada. Para subir a API /query: bash scripts/bootstrap-w01.sh --with-api${RST}"
  else
    say "  ${DIM}Pulada (o agente lê via SQL direto e não precisa dela).${RST}"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# banner final
# ─────────────────────────────────────────────────────────────────────────────
printf "\n${BOLD}${GRN}"
cat <<'DONE'
╔══════════════════════════════════════════════════════════════════╗
║   ✓ W01 PRONTO — o cérebro está vivo e populando                 ║
╚══════════════════════════════════════════════════════════════════╝
DONE
printf "${RST}"
cat <<EOF
  ${BOLD}Portas (host):${RST}
    Postgres (Ledger) ......... localhost:${HOST_PG_PORT}   db=${PG_DB} user=${PG_USER}
    Qdrant  (Memory) .......... localhost:6333
    Neo4j   (Brain) ........... localhost:7474  (browser) / 7687 (bolt)
    SeaweedFS (Lake) .......... localhost:8333 (s3) / 9333 (master)
    API /query (se --with-api). localhost:8000

  ${BOLD}Inspecionar ao vivo:${RST}
    docker compose -f w01-rag/docker-compose.yml ps
    docker exec ${PG_CONTAINER} psql -U ${PG_USER} -d ${PG_DB} -c "SELECT quality_flag, count(*) FROM customers GROUP BY 1;"

  ${BOLD}Próximo passo (o agente W02):${RST}
    cd agent && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    python -m src.guardian.run draw      # desenha a máquina de estados
    python -m src.guardian.run run       # roda contra o Ledger vivo

  ${BOLD}Controle:${RST}
    bash scripts/bootstrap-w01.sh --down   # parar (mantém dados)
    bash scripts/bootstrap-w01.sh --nuke   # zerar tudo (apaga volumes)
EOF
