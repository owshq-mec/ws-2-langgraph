#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# restore.sh — reverte o que seed-red.sh corrompeu (par do gatilho de RED).
#
# Acha os customers marcados com company='__SEED_RED__' e os devolve a um estado
# íntegro: email válido, company plausível, pedidos de volta a 'completed'.
# Idempotente — rodar sem nada marcado não faz nada.
#
# Uso: bash scripts/restore.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PG_CONTAINER="dataops-postgres"
PG_USER="dataops"
PG_DB="dataops"
# Os corrompidos são identificados pelos padrões de email dos seeds (red e yellow).
EMAIL_PATTERN="broken-%-no-at-sign"   # seed-red
YELLOW_PATTERN="yellowseed.%"         # seed-yellow

if [[ -t 1 ]]; then GRN=$'\033[32m'; YLW=$'\033[33m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'
else GRN=""; YLW=""; BOLD=""; DIM=""; RST=""; fi

command -v docker >/dev/null 2>&1 || { echo "docker não encontrado no PATH" >&2; exit 1; }
docker inspect "$PG_CONTAINER" >/dev/null 2>&1 || {
  echo "${YLW}Container $PG_CONTAINER não está rodando — nada a restaurar.${RST}" >&2; exit 0; }

psql() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" "$@"; }

n_marked="$(psql -tAc "SELECT count(*) FROM customers WHERE email LIKE '${EMAIL_PATTERN}' OR email LIKE '${YELLOW_PATTERN}';" | tr -d '[:space:]')"
if [[ "${n_marked:-0}" -eq 0 ]]; then
  printf "${DIM}Nenhum customer corrompido (seed-red/seed-yellow) — banco já está limpo.${RST}\n"
  exit 0
fi

printf "${BOLD}▸ Restaurando %s customers corrompidos (red+yellow)…${RST}\n" "$n_marked"
psql -v ON_ERROR_STOP=1 -q <<SQL
-- Zera o veredito do agente (quality_flag/health_score/checked_at) ANTES de reescrever
-- o email — senão o filtro por padrão de email não casaria mais. Sem isso, o customer
-- volta a ter dados íntegros mas carrega uma flag 'red'/'yellow' presa do run anterior
-- (flag órfã), e como o agente só re-pontua a janela recente, ids antigos ficariam
-- marcados pra sempre. Devolve a linha ao estado PRÉ-agente (não-pontuado, flag nula).
UPDATE customers
   SET health_score = NULL,
       quality_flag = NULL,
       checked_at   = NULL
 WHERE email LIKE '${EMAIL_PATTERN}' OR email LIKE '${YELLOW_PATTERN}';

-- seed-red: devolve os pedidos falhos a 'completed'
UPDATE orders o
   SET status = 'completed'
  FROM customers c
 WHERE o.customer_id = c.id
   AND c.email LIKE '${EMAIL_PATTERN}'
   AND o.status = 'failed';

-- seed-yellow: remove os pedidos INJETADOS pelo seed (ele apaga e injeta 1 completed + 1 failed)
DELETE FROM orders o
 USING customers c
 WHERE o.customer_id = c.id
   AND c.email LIKE '${YELLOW_PATTERN}';

-- devolve email/company a um estado íntegro (determinístico por id)
UPDATE customers
   SET email   = 'restored.' || id || '@example.com',
       company = 'Acme Corp'
 WHERE email LIKE '${EMAIL_PATTERN}' OR email LIKE '${YELLOW_PATTERN}';
SQL

printf "${GRN}✓ Restaurado.${RST} Rode o agente de novo — deve voltar ao caminho green/yellow.\n"
printf "${DIM}(dica: 'bash scripts/seed-red.sh' p/ forçar o RED de novo no próximo ensaio)${RST}\n"
