# Prompt 03 — Regras de qualidade (scoring)

## Context

O agente precisa de uma forma de decidir se um dado é saudável. Mantemos as regras como
**lógica pura** (sem I/O, sem LLM) num módulo próprio — assim é testável em isolamento e
aparece limpa no slide. O grafo chama isto no nó `score`.

## Objective

Criar `src/guardian/scoring.py`.

## Requirements

- `evaluate_row(row: dict) -> tuple[float, list[str]]` — aplica regras a um customer, retorna
  (health_score 0..1, violações). Regras:
  - email ausente ou sem `@` → `-0.5` (+ violação "email inválido/ausente")
  - `company` nula → `-0.15` (+ violação "company nula")
  - taxa de pedidos com falha (`failed_orders/n_orders`) → penalidade `min(0.4, fail_ratio)` (+ violação "X% dos pedidos falharam")
  - score final = `max(0.0, round(score, 3))`.
- `flag_for(score: float) -> str` — `green` se `>= GREEN_AT`, `yellow` se `>= YELLOW_AT`, senão `red`.
- `aggregate(rows: list[dict]) -> dict` — pontua o conjunto; retorna:
  - `scored`: `[(id, score, flag), ...]`
  - `violations`: lista achatada
  - `dataset_health`: média dos scores (round 3)
  - `dataset_flag`: `flag_for(dataset_health)`
  - `n_red`, `n_yellow`: contagem de registros individuais por flag.

## Verification

```bash
python -c "
from src.guardian import scoring
print(scoring.evaluate_row({'id':1,'email':'a@b.com','company':'X','n_orders':2,'failed_orders':0}))  # (1.0, [])
print(scoring.evaluate_row({'id':2,'email':'broken','company':None,'n_orders':2,'failed_orders':2}))  # score baixo, 3 violações
print(scoring.flag_for(0.95), scoring.flag_for(0.6), scoring.flag_for(0.2))  # green yellow red
"
```
