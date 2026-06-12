#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# seed-yellow.sh — corrompe DE LEVE os customers recentes p/ cair na faixa YELLOW
# e disparar o loop de auto-correção (evaluator-optimizer) ao vivo.
#
# Diferença p/ o seed-red: aqui o dano é PARCIAL (não derruba pra RED). O objetivo
# é um score na faixa 0.5–0.8 → flag yellow → o grafo entra em optimize→evaluate.
#
# Como chegamos no yellow (ver scoring.py):
#   - company NULL            → -0.15
#   - alguns pedidos 'failed' → penalidade proporcional (até -0.4)
#   email é mantido VÁLIDO (senão -0.5 já jogaria pra red).
#   Alvo: ~0.55–0.7 (yellow). O optimize vai propor company; o evaluate julga.
#
# Uso:
#   bash scripts/seed-yellow.sh        # 2 customers em yellow
#   bash scripts/seed-yellow.sh 3      # 3 customers
#   bash scripts/restore.sh            # reverte (mesmo restore do seed-red)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

N="${1:-2}"
PG_CONTAINER="dataops-postgres"
PG_USER="dataops"
PG_DB="dataops"
# Rastreado pelo padrão de email — o restore.sh reverte por ele. Para o yellow,
# o email fica VÁLIDO mas com um sufixo identificável que o restore reconhece.
YELLOW_TAG="yellowseed"

if [[ -t 1 ]]; then YLW=$'\033[33m'; GRN=$'\033[32m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'
else YLW=""; GRN=""; BOLD=""; DIM=""; RST=""; fi

command -v docker >/dev/null 2>&1 || { echo "docker não encontrado no PATH" >&2; exit 1; }
docker inspect "$PG_CONTAINER" >/dev/null 2>&1 || {
  echo "Container $PG_CONTAINER não está rodando. Rode: bash scripts/bootstrap-w01.sh" >&2; exit 1; }

psql() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" "$@"; }

printf "${BOLD}${YLW}▸ Rebaixando os %s customers mais recentes p/ YELLOW (disparar auto-correção)…${RST}\n" "$N"

# Alvo: os N customers mais recentes (DENTRO da janela do agente, id DESC). Os mais novos
# costumam ter 0 pedidos — então GARANTIMOS o cenário yellow injetando 3 pedidos por
# customer (2 completed + 1 failed = 33% de falha → penalidade -0.33) + company NULL (-0.15)
# → score ~0.52 → YELLOW. (Cálculo: 1.0 - 0.15 - min(0.4, 0.33) = 0.52, faixa yellow 0.5–0.8.)
# 50% de falha custaria -0.4 e cairia em red — por isso 1 falho de 3, não de 2.
psql -v ON_ERROR_STOP=1 -q <<SQL
WITH target AS (
  SELECT id FROM customers ORDER BY id DESC LIMIT ${N}
)
UPDATE customers c
   SET email   = '${YELLOW_TAG}.' || c.id || '@example.com',
       company = NULL
  FROM target t
 WHERE c.id = t.id;

-- limpa pedidos pré-existentes (idempotência) e injeta 2 completed + 1 failed (33% falha)
WITH target AS (
  SELECT id FROM customers ORDER BY id DESC LIMIT ${N}
)
DELETE FROM orders o USING target t WHERE o.customer_id = t.id;

WITH target AS (
  SELECT id FROM customers ORDER BY id DESC LIMIT ${N}
),
prod AS (SELECT id FROM products WHERE active = TRUE ORDER BY id LIMIT 1)
INSERT INTO orders (customer_id, product_id, amount, quantity, status)
SELECT t.id, p.id, 100.00, 1, s.status
FROM target t CROSS JOIN prod p
CROSS JOIN (VALUES ('completed'), ('completed'), ('failed')) AS s(status);
SQL

printf "${GRN}✓ Rebaixados p/ yellow.${RST} (company nula + ~50%% pedidos falhos, email válido)\n"
psql -q -c "SELECT id, left(email,28) AS email, company FROM customers WHERE email LIKE '${YELLOW_TAG}.%' ORDER BY id DESC;"

printf "\n${DIM}Agora rode o agente — ele deve entrar no loop optimize→evaluate:${RST}\n"
printf "  cd agent && .venv/bin/python -m src.guardian.run run --thread yellow-demo\n"
printf "${DIM}Reverter:${RST} bash scripts/restore.sh\n"
