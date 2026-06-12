# Prompt 06 — Checkpointing (memória durável)

## Context

Até aqui o estado vive só na execução. Agora damos **memória durável** ao agente: o checkpointer
salva o estado a cada passo, indexado por `thread_id`. Isso é o que permite pausar, retomar e
inspecionar — e é pré-requisito do human-in-the-loop (próximo prompt).

> Demo de impacto: rode, **mate o processo**, rode `resume`/`get_state` na MESMA thread — o agente
> continua de onde parou. Esse é o momento "uau" do checkpointing.

## Objective

Ligar um checkpointer ao grafo no `run.py` e demonstrar persistência por thread.

## Requirements

- Em `run.py`, criar `_checkpointer()` com `SqliteSaver(sqlite3.connect("guardian_checkpoints.db",
  check_same_thread=False))`. (Mencionar que `PostgresSaver` usaria o mesmo Postgres do W01 —
  `from_conn_string` + `.setup()` na 1ª vez — mas Sqlite basta p/ o workshop.)
- `cmd_run` passa `checkpointer=_checkpointer()` ao `build_graph` e usa `thread_id` do `--thread`.
- Após o stream, `graph.get_state(config)`: se `snap.next` não vazio → imprimir "[PAUSADO em ...]"
  com instrução de resume; senão "[CONCLUÍDO]".
- Adicionar subcomando `resume --thread T --decision approve|override` (vai ser usado no próximo prompt;
  por ora pode chamar `graph.stream(Command(resume=decision), config, ...)`).

## Verification

```bash
python -m src.guardian.run run --thread t1     # roda e persiste o estado em t1
python -c "
import sqlite3; from src.guardian.run import _checkpointer
print('checkpoints na thread t1:', sqlite3.connect('guardian_checkpoints.db').execute(\"select count(*) from checkpoints where thread_id='t1'\").fetchone())
"
```
Deve haver checkpoints persistidos para a thread. (No próximo prompt o resume ganha sentido com o HITL.)
