#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# seed-red.sh — corrompe de propósito os customers mais recentes p/ disparar o
# human-in-the-loop ao vivo de forma DETERMINÍSTICA.
#
# Por quê: o dado orgânico do W01 quase nunca gera um RED (a média é alta, ~0.99).
# Para o clímax do workshop (grafo PAUSA no interrupt) ser confiável e cronometrável,
# forçamos o RED em N customers que caem DENTRO da janela de validação (id DESC).
#
# Regras de qualidade afetadas (ver scoring.py):
#   - email sem '@'      → -0.5   (regra 1)
#   - company NULL       → -0.15  (regra 2)
#   - orders 'failed'    → penalidade proporcional (regra 3)
# Combinadas, derrubam o score abaixo do YELLOW_AT (0.5) → flag RED → needs_human.
#
# Uso:
#   bash scripts/seed-red.sh          # corrompe os 2 customers mais recentes
#   bash scripts/seed-red.sh 3        # corrompe os 3 mais recentes
#   bash scripts/restore.sh           # reverte (par deste script)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

N="${1:-2}"                       # quantos customers corromper
PG_CONTAINER="dataops-postgres"
PG_USER="dataops"
PG_DB="dataops"
# Rastreamos os corrompidos pelo PADRÃO de email ('broken-<id>-no-at-sign'), não por
# um marcador em company — porque company precisa ficar NULL (é a regra 2 do score).
EMAIL_PATTERN="broken-%-no-at-sign"

if [[ -t 1 ]]; then RED=$'\033[31m'; GRN=$'\033[32m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'
else RED=""; GRN=""; BOLD=""; DIM=""; RST=""; fi

command -v docker >/dev/null 2>&1 || { echo "docker não encontrado no PATH" >&2; exit 1; }
docker inspect "$PG_CONTAINER" >/dev/null 2>&1 || {
  echo "${RED}Container $PG_CONTAINER não está rodando.${RST} Rode antes: bash scripts/bootstrap-w01.sh" >&2; exit 1; }

psql() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" "$@"; }

printf "${BOLD}${RED}▸ Corrompendo os %s customers mais recentes (forçar RED)…${RST}\n" "$N"

# Corrompe os N customers de maior id (os mais recentes — caem na janela do agente).
# email sem '@' (-0.5) + company NULL (-0.15) = score 0.35 → abaixo de YELLOW_AT (0.5) → RED.
# (orders também viram 'failed', mas o RED já está garantido só com email+company.)
psql -v ON_ERROR_STOP=1 -q <<SQL
WITH target AS (
  SELECT id FROM customers ORDER BY id DESC LIMIT ${N}
)
UPDATE customers c
   SET email   = 'broken-' || c.id || '-no-at-sign',
       company = NULL
  FROM target t
 WHERE c.id = t.id;

-- marca os pedidos desses customers como 'failed' (reforço da regra 3, quando há orders)
UPDATE orders o
   SET status = 'failed'
  FROM customers c
 WHERE o.customer_id = c.id
   AND c.email LIKE '${EMAIL_PATTERN}';
SQL

printf "${GRN}✓ Corrompidos.${RST} Customers afetados (email quebrado + company NULL → RED):\n"
psql -q -c "SELECT id, left(email,28) AS email, company FROM customers WHERE email LIKE '${EMAIL_PATTERN}' ORDER BY id DESC;"

printf "\n${DIM}Agora rode o agente — ele deve PAUSAR no human-in-the-loop:${RST}\n"
printf "  cd agent && .venv/bin/python -m src.guardian.run run --thread red-demo\n"
printf "${DIM}Para reverter:${RST} bash scripts/restore.sh\n"
