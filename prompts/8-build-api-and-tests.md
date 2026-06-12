# Prompt 08 — API programática + testes

## Context

O grafo funciona pela CLI. Para o MCP e a UI consumirem o agente, precisamos de uma **API
programática** — uma função que roda o grafo e devolve um resultado estruturado, lidando com o
HITL. E fechamos a fundação com testes da lógica de qualidade.

## Objective

Criar `src/guardian/api.py` e `tests/test_scoring.py`.

## Requirements

### `api.py`
- `@dataclass GuardianResult`: `dataset, thread_id, status ("completed"|"paused"), steps: list[str],
  health_score, quality_flag, n_red, rows_checked, interrupt: Optional[dict]`. Método `summary() -> str`.
- `_collect(graph, stream_input, config) -> GuardianResult`: roda `graph.stream(stream_mode="updates")`,
  acumula os nós em `steps`, captura `__interrupt__`; ao fim usa `graph.get_state` — se `snap.next` →
  status `"paused"` (com `interrupt`), senão `"completed"`.
- `run_guardian(dataset="customers", thread_id="default", auto_approve=None) -> GuardianResult`:
  monta grafo c/ checkpointer Sqlite, roda; se `paused` e `auto_approve in ("approve","override")`,
  chama `resume_guardian`.
- `resume_guardian(thread_id, decision="approve") -> GuardianResult`: retoma com `Command(resume=decision)`.

### `tests/test_scoring.py` (pytest, lógica pura, sem I/O)
- row limpo → score 1.0, flag green.
- email quebrado → score baixo, violação de email.
- failed orders penalizam (bad < clean).
- `aggregate` conta reds (row totalmente corrompido → n_red ≥ 1).
- roteador 1 (`route_after_decide`): red → "human_gate"; yellow c/ hardening < cap → "optimize";
  yellow esgotado / green → "recommend".
- roteador 2 (`route_after_evaluate`): aceito → "validate_rules"; rejeitado c/ orçamento → "optimize";
  esgotado → "human_gate".
- camada LLM (fallback, roda sem chave): `recommend` agrupa violações; `propose_fix` conserta
  email/company; `judge_fix` aceita patch bom e rejeita patch ruim.

## Verification

```bash
python -c "from src.guardian.api import run_guardian; r=run_guardian(thread_id='api'); print(r.status, r.summary())"
python -m pytest tests/ -q     # tudo verde
```
