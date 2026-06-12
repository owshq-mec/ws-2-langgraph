# Prompt 09 — MCP server (o agente vira ferramenta)

## Context

No W01, o RAG virou um MCP consumível por qualquer LLM. Fazemos o mesmo aqui: o **agente stateful
inteiro** (grafo + HITL + checkpoint) vira 3 tools MCP. Agora o Claude Code/Desktop pode validar a
qualidade do catálogo em linguagem natural.

> Fecha o arco do curso: "o RAG virou ferramenta do agente (W01→W02); agora o agente vira ferramenta
> que a Crew do W03 vai orquestrar."

## Objective

Criar `src/guardian/mcp_server.py` (FastMCP, stdio) e `mcp-config.json`.

## Requirements

### `mcp_server.py`
- `from mcp.server.fastmcp import FastMCP`; `mcp = FastMCP("quality-guardian")`.
- 3 tools (cada uma com docstring clara — vira a descrição que o LLM lê):
  - `validate_dataset(dataset="customers", thread_id="mcp") -> str`: chama `run_guardian`; retorna o
    `summary()` + passos; se `paused`, instrui chamar `resume_validation`.
  - `resume_validation(thread_id, decision="approve") -> str`: chama `resume_guardian`.
  - `quality_report() -> str`: `ledger.count_by_flag()` formatado; destaca quantos RED (trigger do W03).
- `main()`: `mcp.run(transport="stdio")`. Entry `python -m src.guardian.mcp_server`.

### `mcp-config.json`
- Bloco `mcpServers.quality-guardian` com `args: ["-m","src.guardian.mcp_server"]`,
  `cwd` (path absoluto do agente), env `GUARDIAN_PG_HOST=localhost`, `GUARDIAN_PG_PORT=5442`.
- ⚠️ **`command` = caminho ABSOLUTO do python do venv** (`.venv/bin/python`), NÃO `"python"` genérico.
  O processo MCP pode não ter o venv no PATH → `FileNotFoundError: python`. (Armadilha pega no ensaio.)

## Verification

```bash
# handshake via cliente MCP (langchain-mcp-adapters):
python -c "
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
async def m():
    c = MultiServerMCPClient({'g':{'command':'python','args':['-m','src.guardian.mcp_server'],'transport':'stdio'}})
    tools = await c.get_tools(); print('tools:', [t.name for t in tools])
    rep = next(t for t in tools if t.name=='quality_report'); print(await rep.ainvoke({}))
asyncio.run(m())
"
```
Deve listar `validate_dataset, resume_validation, quality_report` e imprimir a distribuição do Ledger.
Depois: registrar no Claude Code (`claude mcp add` ou colar o mcp-config.json) e perguntar em linguagem natural.
