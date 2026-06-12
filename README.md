# W02 — LangGraph + LangChain · "Orquestra com Estado"

Workshop ao vivo da Formação AI Data Engineer. Instrutor: Rafael R.
Constrói o **Quality Guardian Agent**: agente stateful (LangGraph) que valida a qualidade do
catálogo do W01 e grava health scores de volta no Ledger — o trigger da Crew do W03.

> **Não é um módulo de slides.** É um projeto construído ao vivo, prompt-a-prompt, dirigindo o
> Claude Code (agentic dev). Você constrói o agente do zero, colando os prompts em `prompts/`.

## Os 4 conceitos (do card), todos materializados

**stateful** (StateGraph + reducers) · **conditional branching** (2 roteadores) ·
**self-correction** (evaluator-optimizer: gerador fraco propõe → avaliador forte julga → converge) ·
**checkpointing** (mata e retoma) — mais **human-in-the-loop** e o **nó LLM** (LangChain).

## Como navegar

| Arquivo / pasta | O que é |
|---|---|
| **`SETUP-ALUNO.md`** | **Comece aqui.** O que fazer após clonar (subir o W01, preparar o scaffold). |
| `aluno/` | **Seu ponto de partida** (`src/guardian/` vazio): onde você constrói o agente colando os prompts. |
| `prompts/` | **Os 11 prompts** que você cola no Claude Code ao vivo (= `aluno/prompts/`). |
| `scripts/` | `bootstrap-w01` (sobe o W01), `seed-red`/`seed-yellow`/`restore` (gatilhos), `studio` (LangGraph Studio). |
| `w01-rag/` | O projeto W01 (dependência; sobe a infra que o agente consome). |
| `sketch/plan.md` | Arquitetura técnica + sequência de build. |

## Quickstart

> Veja `SETUP-ALUNO.md` para o passo a passo completo. Você constrói o agente do zero em `aluno/`
> colando os prompts no Claude Code. Os comandos abaixo assumem o agente já construído.

```bash
# 1. subir o W01 (a infra que o agente consome) — UM comando
bash scripts/bootstrap-w01.sh                    # Postgres no host :5442, dado vivo

# 2. preparar o ambiente
cd aluno && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
pip install -e .                                 # registra o pacote (p/ o Studio)

# 3. desenhar + rodar (caminho green)
python -m src.guardian.run draw                  # a máquina de estados
python -m src.guardian.run run --thread demo     # roda contra o Ledger do W01

# 4. auto-correção (yellow → o loop converge pra green)
cd .. && bash scripts/seed-yellow.sh 2 && cd aluno
python -m src.guardian.run run --thread yellow
cd .. && bash scripts/restore.sh && cd aluno

# 5. human-in-the-loop (red → pausa → resume)
cd .. && bash scripts/seed-red.sh 2 && cd aluno
python -m src.guardian.run run --thread red       # PAUSA no interrupt
python -m src.guardian.run resume --thread red --decision approve
cd .. && bash scripts/restore.sh && cd aluno

# 6. a 2ª lente (LangGraph Studio)
cd .. && bash scripts/studio.sh

# testes (a qualquer momento)
python -m pytest tests/ -q                        # 11/11 verde
```

## O grafo (o que a turma constrói)

```
START → check_schema → validate_rules → score
                            ▲                │
                            │       green ───┼── yellow ──── red
                            │         │      │      │         │
                            │     recommend  │  optimize   human_gate ⏸
                            │         │      │  (Haiku)       │ (interrupt)
                            │         ▼      │      ▼         │
                       (re-pontua) write_ledger  evaluate ───┘
                            │                 (Sonnet)
                            └──── aceito ◄────────┘
                                                rejeita ↺ optimize · esgota → human_gate
```

Cada conceito do card materializado: nós+estado · arestas condicionais · **evaluator-optimizer**
(auto-correção real) · checkpointing · human-in-the-loop — visível em 2 lentes (terminal + Studio).

## Premissa (importante)

Os alunos **já viram** o Luan construir o W01 (setup, RAG, MCP). Este workshop **não repete isso** —
começa com o W01 rodando e constrói só o agente LangGraph. Todo o tempo ao vivo é conceito novo.
