# Prompt 04 — O primeiro grafo (linha reta)

## Context

Agora o coração: a **máquina de estados**. Começamos com o fluxo LINEAR — sem branching, sem
ciclos ainda — só para o aluno VER um StateGraph rodar fim-a-fim e o estado fluir.

> Narrar: "isto é abrir a caixa-preta do ReAct que vocês usaram no W01. Lá o agente decidia
> sozinho num loop que vocês não viam. Aqui a gente DESENHA o grafo, com estado explícito."

## Objective

Criar `src/guardian/graph.py` (versão linear) e `src/guardian/run.py` (CLI draw/run).

## Requirements

### `graph.py` (versão 1 — linear)
Nós (cada um função `(state) -> dict`, retornando atualização parcial + uma mensagem em `messages`):
- `check_schema`: usa `ledger.get_columns` e `EXPECTED_COLUMNS`; seta `schema_ok`.
- `validate_rules`: `ledger.read_customers()` (já aplica a JANELA) + `scoring.aggregate()`; seta
  `rows_checked`, `rule_violations`, `health_score`, `n_red`, `n_yellow`, `_scored`, `_rows`.
- `score` (**individual-aware** — a média mascara casos individuais): `quality_flag = "red" if n_red>0
  else "yellow" if n_yellow>0 else flag_for(health)`; seta `needs_human = (flag=="red")`.
  > Por quê: com 50 linhas, 1 cliente corrompido vira ~0.99 na média e passaria mascarado. O flag
  > dispara no INDIVÍDUO, não só na média.
- `write_ledger`: `ledger.ensure_quality_columns()` + `ledger.write_scores(state["_scored"])`;
  loga distribuição (`ledger.count_by_flag()`); seta `written=True`.
- `build_graph(checkpointer=None)`: StateGraph linear
  `START → check_schema → validate_rules → score → write_ledger → END`. `compile(checkpointer=...)`.

### `run.py` (CLI)
- `draw`: `print(graph.get_graph().draw_ascii())` e `draw_mermaid()`.
- `run [--thread] [--plain]`: `graph.stream(initial_state("customers"), config, stream_mode="updates")`,
  renderizando o delta de cada nó (o "assistir o agente pensar"). `config={"configurable":{"thread_id":...}}`.

### `render.py` (renderer turbinado — a camada visual da demo)
- Um `RichRenderer` (com `rich`) que consome cada chunk do stream e desenha um painel:
  **breadcrumb** do caminho percorrido (ícone + cor por nó) + tabela do **estado vivo** (campos do
  GuardianState, coloridos por valor: green/yellow/red, ✓/✗ para bools) + painel vermelho de
  **DECISÃO NECESSÁRIA** quando há interrupt.
- Fallback `PlainRenderer` (ANSI puro) se `rich` não estiver disponível — o agente nunca quebra por
  causa da camada visual. `make_renderer(rich=True)` escolhe.
- `run.py` usa o `RichRenderer` por padrão; `--plain` força o modo simples.
- Ícones/cores por nó (paleta da casa): check_schema=cyan🔍, validate_rules=yellow📋, score=magenta⚖️,
  optimize=yellow🛠️, evaluate=magenta🧪, recommend=blue🧠, human_gate=red⏸️, write_ledger=green💾.

> Desacoplado de propósito: a lógica do agente (graph.py) não sabe nada de apresentação. O render é
> só uma LENTE sobre o stream. (O LangGraph Studio será outra lente sobre o mesmo grafo.)

## Verification

```bash
python -m src.guardian.run draw     # desenha a máquina de estados (ASCII + mermaid)
python -m src.guardian.run run      # roda contra o Ledger do W01 e grava health scores
docker exec dataops-postgres psql -U dataops -d dataops -c \
  "SELECT quality_flag, count(*) FROM customers GROUP BY quality_flag;"
```
Deve desenhar o grafo, rodar os 4 nós em sequência, e gravar flags no Ledger real.
