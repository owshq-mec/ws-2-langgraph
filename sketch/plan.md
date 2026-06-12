# Quality Guardian Agent — Project Plan (W02)

## Vision

O W02 dá **inteligência** ao cérebro construído no W01. Onde o W01 entregou um RAG que
*responde* perguntas (DataOps Knowledge Hub), o W02 entrega um agente **stateful** que
*age*: percorre o catálogo, valida a qualidade de cada dataset por um **grafo de estados
explícito**, se auto-corrige, pede aprovação humana quando o risco é alto, e **grava
health scores de volta no Ledger** — o gancho que dispara a Crew do W03.

> A diferença entre **saber** e **agir** é o **estado**. LangGraph é a máquina de estados
> que torna o raciocínio do agente explícito, inspecionável e durável.

## Posição no arco do curso

`W01 Constrói o Cérebro` → **`W02 Dá Inteligência`** → `W03 Escala com Equipe (CrewAI)`

- **Consome do W01:** o Ledger (Postgres), e opcionalmente a API `/query` e o MCP do W01.
- **Entrega pro W03:** `quality_flag = "red"` no Ledger = trigger da Crew.

## Premissa do workshop (o que NÃO se reconstrói)

Os alunos **já viram** o Luan construir o W01 (CLAUDE.md, scaffold, Docker, RAG, MCP) no
workshop anterior. **Não repetimos isso.** O ponto de partida do W02 é:

- W01 **já rodando** (`docker compose up` em `w01-rag/`; Postgres no host :5442).
- Scaffold mínimo do agente já presente (pasta `src/guardian/` vazia + venv + requirements).

Todo o tempo ao vivo é **LangGraph puro**: do primeiro nó até o agente exposto como MCP/UI.

## Architecture: a máquina de estados

```
START → check_schema → validate_rules → score → decide
                            ▲                       ├── red    → human_gate (interrupt) → write_ledger → END
                            └── bump_retry ◄── yellow├── yellow → loop (auto-correção, até MAX_RETRIES)
                                                     └── green  → write_ledger → END
```

| Nó | Papel | Conceito LangGraph |
|---|---|---|
| `check_schema` | schema do dataset está íntegro? | nó simples (gate) |
| `validate_rules` | lê dados + aplica regras de qualidade | nó com I/O (tool) |
| `score` | health → flag; marca needs_human | nó de decisão |
| `decide` (roteador) | green/yellow/red → próximo passo | **aresta condicional** |
| `bump_retry` → `validate_rules` | tentar de novo | **ciclo / auto-correção** |
| `human_gate` | pausa p/ aprovação humana | **human-in-the-loop (interrupt)** |
| `write_ledger` | grava health_score/quality_flag no W01 | nó de escrita (handoff W03) |
| (compile) | estado persistido a cada passo | **checkpointing** |

## Stack

| Componente | Tecnologia | Versão (jun/2026) |
|---|---|---|
| Orquestração / grafo | LangGraph | 1.2.4 |
| Peças (modelo, tools, msgs) | LangChain | 1.3.4 |
| LLM do agente | langchain-anthropic (Claude) | 1.4.4 |
| Checkpointing | langgraph-checkpoint-sqlite / -postgres | 3.1.0 |
| Acesso ao Ledger | psycopg | 3.3.4 |
| Consumir MCP do W01 (opcional) | langchain-mcp-adapters | 0.2.2 |
| Expor o agente como tool | mcp (FastMCP) | 1.27 |
| UI conversacional | chainlit | 2.11 |
| Runtime | Python | 3.11+ |

## Pontos de integração com o W01 (provados)

- **LER (factual):** SQL direto no Postgres `dataops` (host :5442). Determinístico, sem custo de LLM.
- **LER (semântico/relacional, opcional):** `POST localhost:8000/api/v1/query` (precisa OPENAI_API_KEY no W01).
- **ESCREVER:** `ALTER TABLE customers ADD COLUMN health_score/quality_flag` + UPDATE. O W01 não
  tem API de escrita — esta é a parte aditiva do W02. (As colunas novas ficam visíveis ao text-to-SQL do W01.)

## Build Sequence (prompts ao vivo)

O agente é construído prompt-a-prompt no Claude Code (agentic dev). Cada prompt produz código
que **roda e se vê rodando** (grafo desenhado, estado no stream, checkpoint retomado).

1. **CLAUDE.md** do agente (contrato: LangGraph, regras, conexão ao W01)
2. **State + Ledger tools** (GuardianState; ler/escrever o Postgres do W01)
3. **Regras de qualidade** (scoring puro, testável)
4. **Primeiro grafo** (check_schema → validate → score → write) — roda fim-a-fim
5. **Aresta condicional + ciclo** (decide → auto-correção)
6. **Checkpointing** (SqliteSaver/PostgresSaver; matar e retomar)
7. **Human-in-the-loop** (interrupt/resume — o clímax)
8. **API programática + testes** (run_guardian; pytest)
9. **MCP server** (o agente vira ferramenta — 3 tools)
10. **UI Chainlit** (interface conversacional + botões de aprovação)

## Success Criteria

- [ ] `run draw` desenha a máquina de estados (ASCII + mermaid)
- [ ] `run run` executa contra o Ledger do W01 e grava health scores
- [ ] caso RED → grafo **pausa** no `interrupt()`; `resume` retoma do checkpoint
- [ ] loop de auto-correção respeita `MAX_RETRIES` (sem loop infinito)
- [ ] MCP server expõe `validate_dataset`/`resume_validation`/`quality_report`
- [ ] Chainlit roda o agente e mostra o HITL com botões
- [ ] `quality_flag="red"` no Ledger = trigger pronto p/ o W03
- [ ] `pytest` verde

## Design Decisions

- **StateGraph à mão, não `create_react_agent`.** O card pede "máquina de estados explícita".
  Construímos os nós/arestas para o aluno VER a máquina — abrindo a caixa-preta do ReAct que ele
  usou no W01.
- **SQL direto p/ ler dados factuais** (rápido, determinístico, sem chave). `/query` do W01 fica
  como enriquecimento semântico opcional.
- **HITL só em RED.** Política: gravar um RED é ação de risco → exige humano. Green/yellow fluem sozinhos.
- **Média de dataset mascarava reds individuais** → política corrigida: HITL dispara se houver
  QUALQUER registro RED, não só se a média for baixa. (Achado real durante o build — vira lição.)

## Connection to Formation

W02 transforma o RAG estático do W01 num sistema que **age sobre os próprios dados**. O `quality_flag`
que o Guardian grava é exatamente o sinal que a Crew do W03 (Monitor → Diagnostician → Remediator →
Reporter) consome para agir. Nenhum workshop é ilha.
