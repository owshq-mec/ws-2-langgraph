# Prompt 07 — Human-in-the-loop (o clímax)

## Context

Gravar um dataset RED é uma ação de risco. O agente deve **parar e perguntar ao humano** antes.
Este é o conceito mais impressionante do workshop: o grafo **pausa no meio da execução**, devolve
o controle, e retoma exatamente de onde parou — graças ao checkpointing do prompt anterior.

> API atual (jun/2026): `interrupt()` dentro do nó + `Command(resume=...)` p/ retomar.
> NÃO usar `interrupt_before` no compile (virou só debug).

## Objective

Transformar o `human_gate` num nó real com `interrupt()` e fechar o ciclo de resume.

## Requirements

- `human_gate(state) -> Command` usando `from langgraph.types import interrupt, Command`:
  ```python
  decision = interrupt({
      "question": f"Dataset '{state['dataset']}' está RED (health={state['health_score']}). Aprovar gravação?",
      "violations": state["rule_violations"],
      "options": ["approve", "override"],
  })
  if decision == "override":
      return Command(update={"human_decision":"override","quality_flag":"yellow"}, goto="recommend")
  return Command(update={"human_decision":"approve"}, goto="recommend")
  ```
  > `goto="recommend"`: o caminho HITL também passa pelo diagnóstico (nó LLM) antes de gravar.
- `write_ledger`: se `human_decision == "override"`, rebaixar os reds individuais p/ yellow antes de gravar.
- `run.py`: ao detectar pausa (`snap.next`), instruir o resume. `resume` usa `Command(resume=decision)`.
- O `interrupt` precisa de checkpointer (já temos) — confirmar que `human_gate` está no grafo e que
  o roteador manda RED p/ ele.

## Verification

```bash
# força um RED de forma determinística (corrompe os 2 mais recentes, dentro da janela):
cd .. && bash scripts/seed-red.sh 2 && cd agent
python -m src.guardian.run run --thread red1       # deve PAUSAR no interrupt (mostra as violações)
python -m src.guardian.run resume --thread red1 --decision approve   # retoma do checkpoint e grava
docker exec dataops-postgres psql -U dataops -d dataops -c "SELECT quality_flag, count(*) FROM customers GROUP BY 1;"
cd .. && bash scripts/restore.sh && cd agent   # restaura
```
Esperado: 1º comando PAUSA no interrupt; resume retoma do checkpoint e grava os RED. A distribuição
mostra `red`. (`restore.sh` reverte o seed.)
