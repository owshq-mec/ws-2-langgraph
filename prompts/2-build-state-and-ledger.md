# Prompt 02 — State + Ledger tools

## Context

Com o CLAUDE.md pronto, vamos criar as duas fundações do agente: o **State** (a memória de
trabalho do grafo) e o acesso ao **Ledger** do W01 (ler dados e gravar health scores).

Conceito-chave para narrar: em LangGraph, o State é um `TypedDict` que cada nó lê e atualiza.
Os campos com `Annotated[tipo, reducer]` definem COMO a atualização é fundida. `add_messages`
faz append inteligente; campos sem reducer são sobrescritos.

> Decisão de design importante (a JANELA): o generator do W01 nunca para — o Ledger acumula dezenas
> de milhares de linhas. Validar a tabela inteira (a) mascara casos individuais na média e (b) deixa
> o estado ilegível. Então o agente valida só os **N mais recentes** (`id DESC`). Postura de produção:
> "você valida o lote que acabou de chegar, não o histórico inteiro."

## Objective

Criar `src/guardian/config.py`, `src/guardian/state.py` e `src/guardian/ledger.py`.

## Requirements

### `config.py`
- **Carregar o `.env` no topo do módulo** (antes de qualquer `os.getenv`): `from dotenv import
  load_dotenv; load_dotenv()`. Como `config` é importado por todos os entrypoints (CLI, Chainlit,
  MCP, testes), a `ANTHROPIC_API_KEY` do `.env` entra no ambiente para todos eles. Import defensivo
  (`try/except ModuleNotFoundError: pass`) p/ não quebrar se `python-dotenv` faltar. Pinar
  `python-dotenv` no `requirements.txt`.
- Conexões via env var com defaults do setup local:
  - Postgres do W01 no HOST: `GUARDIAN_PG_HOST=localhost`, `GUARDIAN_PG_PORT=5442`,
    db/user/password `dataops`/`dataops`/`dataops123`.
  - `PG_CONNINFO` = `postgresql://dataops:dataops123@localhost:5442/dataops?sslmode=disable`.
  - `LLM_MODEL` default `"anthropic:claude-sonnet-4-6"` (via env).
  - **Evaluator-optimizer (usado no prompt 05):** `GENERATOR_MODEL` default
    `"anthropic:claude-haiku-4-5"` (gerador fraco), `EVALUATOR_MODEL` default
    `"anthropic:claude-sonnet-4-6"` (avaliador forte).
  - **Janela:** `WINDOW = int(env "GUARDIAN_WINDOW", default 50)`.
  - `MAX_RETRIES=2`, `RECURSION_LIMIT=25`, `GREEN_AT=0.8`, `YELLOW_AT=0.5`.

### `state.py` — `GuardianState(TypedDict)`
Campos:
- `messages: Annotated[list[AnyMessage], add_messages]` (reducer — canal de conversa)
- `dataset: str` (alvo, ex: "customers")
- `schema_ok: Optional[bool]` · `rows_checked: Optional[int]` · `rule_violations: Optional[list[str]]`
- `n_red: Optional[int]` · `n_yellow: Optional[int]` (registros individuais por flag — dispara o fluxo)
- `health_score: Optional[float]` · `quality_flag: Optional[Literal["green","yellow","red"]]`
- `recommendation: Optional[str]`
- `_scored: Optional[list]` (carona [(id,score,flag)] p/ o write) · `_rows: Optional[list]` (rows
  brutos, carona p/ o `optimize`)
- **Evaluator-optimizer:** `hardening: int` (nº de rejeições do evaluator) ·
  `proposed_fixes: Optional[list]` ([(id, patch)] do gerador) · `eval_feedback: Optional[str]`
  (motivo da rejeição, volta p/ o gerador) · `eval_accepted: Optional[bool]` ·
  `corrected_rows: Optional[list]` (rows corrigidos in-state p/ re-pontuar)
- `retries: int` · `needs_human: bool` · `human_decision: Optional[str]` · `written: Optional[bool]`
- Função `initial_state(dataset="customers") -> GuardianState` com todos os campos zerados
  (`hardening=0`, listas/optionais `None`).

### `ledger.py` — acesso ao Postgres do W01 (psycopg v3, row_factory=dict_row, autocommit)
- `connect()` (contextmanager) usando `config.PG_CONNINFO`.
- `QUALITY_COLUMNS_DDL` + `ensure_quality_columns()`: `ALTER TABLE customers ADD COLUMN IF NOT EXISTS
  health_score NUMERIC(4,3), quality_flag VARCHAR(10), checked_at TIMESTAMP` (idempotente).
- `EXPECTED_COLUMNS = {"id","name","email","plan","company","created_at"}`.
- `get_columns(table) -> set[str]` (lê information_schema — p/ check_schema).
- `read_customers(limit: int | None = None) -> list[dict]`: SELECT com LEFT JOIN orders agregando
  `n_orders`, `total_amount`, `failed_orders` (SUM de status='failed') por customer.
  **Aplica a JANELA:** `ORDER BY c.id DESC LIMIT %s` (default `config.WINDOW`). Valida os N recentes.
- `write_scores(scored: list[tuple[int,float,str]]) -> int`: UPDATE health_score/quality_flag/checked_at
  via `executemany`; retorna rowcount.
- `count_by_flag() -> dict[str,int]`: distribuição de quality_flag (p/ relatório/handoff W03).

## Verification

```bash
. .venv/bin/activate
python -c "from src.guardian import ledger, config; ledger.ensure_quality_columns(); print(len(ledger.read_customers()), 'customers (janela', config.WINDOW, ')'); print(ledger.count_by_flag())"
```
Deve imprimir **50** customers (a janela) — lendo o Ledger REAL do W01 — e a distribuição de flags.
```

> **Narrar:** "Reparem que ele leu só 50, não os 18 mil do banco. Essa é a janela — o agente olha o
> lote recente. E os campos `hardening`/`proposed_fixes`/`corrected_rows` no State já preparam o
> terreno pro evaluator-optimizer que vamos construir no prompt 05."
