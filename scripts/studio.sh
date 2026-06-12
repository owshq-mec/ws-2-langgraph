#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# studio.sh — sobe o LangGraph Studio (a lente visual "produto" do grafo).
#
# Abre o servidor de dev do LangGraph (`langgraph dev`), que serve o Studio:
# o grafo interativo no navegador, execução passo a passo e time-travel de
# checkpoints. Mac-only no app nativo; no navegador funciona via smith.langchain.com.
#
# Pré-req: W01 de pé (bash scripts/bootstrap-w01.sh) e venv do agente instalado.
#
# Uso:
#   bash scripts/studio.sh           # sobe o Studio (abre o navegador)
#   bash scripts/studio.sh --no-open # sobe sem abrir navegador
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/../agent" && pwd)"
PORT="${GUARDIAN_STUDIO_PORT:-2024}"

if [[ -t 1 ]]; then BOLD=$'\033[1m'; CYN=$'\033[36m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
else BOLD=""; CYN=""; GRN=""; YLW=""; RST=""; fi

cd "$AGENT_DIR"

# venv check
[[ -x ".venv/bin/python" ]] || { echo "${YLW}venv não encontrado.${RST} Rode: cd agent && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" >&2; exit 1; }

# langgraph-cli check
if ! .venv/bin/python -c "import langgraph_cli" >/dev/null 2>&1; then
  echo "Instalando langgraph-cli[inmem] no venv…"
  .venv/bin/python -m pip install "langgraph-cli[inmem]" >/dev/null 2>&1
fi

# W01 de pé? (o grafo lê o Ledger ao executar)
if ! docker inspect dataops-postgres >/dev/null 2>&1; then
  echo "${YLW}! W01 não parece estar de pé${RST} — o grafo desenha, mas executar vai falhar na leitura do Ledger."
  echo "  Suba antes: bash scripts/bootstrap-w01.sh"
fi

OPEN_FLAG=""
[[ "${1:-}" == "--no-open" ]] && OPEN_FLAG="--no-browser"

printf "${BOLD}${CYN}▸ Subindo LangGraph Studio em http://127.0.0.1:%s${RST}\n" "$PORT"
printf "  ${GRN}grafo:${RST} quality_guardian  ·  ${GRN}config:${RST} langgraph.json\n"
printf "  Studio (navegador): https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:%s\n\n" "$PORT"

exec .venv/bin/python -m langgraph_cli dev --port "$PORT" $OPEN_FLAG
