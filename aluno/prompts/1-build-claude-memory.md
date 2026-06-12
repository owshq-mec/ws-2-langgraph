# Prompt 01 — CLAUDE.md do Quality Guardian

## Context

Estamos construindo o **Quality Guardian Agent** — o Workshop 2 da formação. É um agente
**stateful** em **LangGraph** que consome o catálogo do W01 (DataOps Knowledge Hub, já rodando),
valida a qualidade dos dados por um grafo de estados, e grava health scores de volta no Ledger
(Postgres do W01) — o trigger da Crew do W03.

O W01 já está de pé: Postgres (Ledger) no host **:5442**, com tabelas `customers/orders/products`.
NÃO vamos reconstruir o W01 — só o agente, em LangGraph.

O plano do projeto está em `sketch/plan.md`.

## Objective

Criar um `CLAUDE.md` na raiz do agente — o contrato entre desenvolvedor e Claude Code para este projeto.

## Requirements

Inclua as seções:

### 1. Project Overview
- Um parágrafo: o que é o Quality Guardian (agente stateful que valida qualidade e grava no Ledger do W01).
- O conceito: **máquina de estados explícita** (LangGraph) com nós, arestas condicionais, ciclos,
  checkpointing e human-in-the-loop.
- O fim: o agente exposto como **MCP + UI Chainlit**, consumível em linguagem natural.

### 2. Tech Stack
- LangGraph 1.2 (grafo/estado), LangChain 1.3 (modelo/tools/mensagens), langchain-anthropic (Claude).
- langgraph-checkpoint-sqlite/postgres (checkpointing), psycopg (Ledger), langchain-mcp-adapters
  (consumir o MCP do W01, opcional), mcp/FastMCP (expor o agente), Chainlit (UI). Python 3.11+.

### 3. Architecture Rules (não-negociáveis)
- O grafo é uma **máquina de estados explícita** — construir StateGraph à mão (NÃO usar
  `create_react_agent`; o objetivo didático é VER os nós/arestas).
- Todo nó é uma função `(state) -> dict` que retorna atualização PARCIAL do state.
- Loops SEMPRE com contador de parada no state (evitar `GraphRecursionError`).
- Human-in-the-loop com `interrupt()` + `Command(resume=...)` (NÃO usar a API antiga
  `interrupt_before` no compile — virou só debug).
- LER dados factuais via SQL direto no Postgres do W01; ESCREVER health_score/quality_flag via SQL
  (o W01 não tem API de escrita).

### 4. Code Standards
- Type hints e docstrings em funções públicas. Layout `src/`. `.env` para segredos.
- Imports do namespace novo: `from langchain.chat_models import init_chat_model`,
  `from langchain.tools import tool`, `from langchain.messages import ...` (não `langchain_core.*`).

### 5. Connection to W01
- Ledger = Postgres `dataops`, host **localhost:5442** (remapeado p/ não conflitar com outros Postgres).
- Conexão: `postgresql://dataops:dataops123@localhost:5442/dataops`.
- Tabelas: `customers(id,name,email,plan,company,created_at)`, `orders(...,status,amount)`, `products(...)`.

### 6. Constraints (proibições)
- ❌ NÃO reconstruir o W01 (RAG/MCP do Luan) — ele já existe e roda.
- ❌ NÃO usar `create_react_agent` no fluxo principal (queremos a máquina de estados explícita).
- ❌ NÃO hardcodar nomes de modelo — ler de env var.
- ❌ NÃO commitar segredos — `.env` é git-ignored.

## Verification

- `CLAUDE.md` existe na raiz com todas as seções.
- A regra "StateGraph à mão, não create_react_agent" está explícita.
