# Prompt 11 — LangGraph Studio (a 2ª lente visual)

## Context

O terminal turbinado já mostra o estado fluindo. O **LangGraph Studio** é a lente "produto": o grafo
interativo no navegador, execução clicável passo a passo, e **time-travel de checkpoints**. É o mesmo
grafo — outra lente. Roda via `langgraph dev` (servidor de dev do LangGraph).

> Use no fecho, depois do agente completo (checkpointing + HITL prontos). No Mac há app nativo; em
> qualquer lugar funciona no navegador via smith.langchain.com apontando pro servidor local.

## Objective

Tornar o agente carregável pelo `langgraph dev`: criar `langgraph.json`, `pyproject.toml` (p/ o pacote
ser descoberto), um entrypoint `studio_graph`, e o script `scripts/studio.sh`.

## Requirements

### `pyproject.toml` (na raiz do projeto)
- Pacote `quality-guardian`, `requires-python >=3.11`, layout `src/` (`package-dir = {"" = "src"}`,
  `packages.find where=["src"]`). Dependências reais ficam no `requirements.txt`; aqui só o mínimo p/
  o `langgraph-cli` descobrir o pacote `guardian`. Instalar com `pip install -e .`.

### `graph.py` — entrypoint do Studio
- `studio_graph(config: RunnableConfig | None = None)`: retorna `build_graph(checkpointer=None)`.
- ⚠️ **DUAS armadilhas (resolver exatamente assim):**
  1. **Compilar SEM checkpointer** — o servidor do Studio gerencia a própria persistência; passar um
     checkpointer quebra com `Invalid checkpointer: dict`.
  2. **Assinatura só com tipos `RunnableConfig`/`ServerRuntime`** — o `langgraph-cli` inspeciona a
     assinatura da factory e rejeita `*args/**kwargs`. Por isso o parâmetro tipado `config`.

### `langgraph.json` (na raiz do projeto)
```json
{
  "dependencies": ["."],
  "graphs": { "quality_guardian": "guardian.graph:studio_graph" },
  "env": "./.env",
  "python_version": "3.11"
}
```
- ⚠️ O grafo é referenciado por **módulo** (`guardian.graph:studio_graph`), NÃO por caminho de arquivo
  — carregar por arquivo quebra os imports relativos (`from . import ...`). Por isso o `pip install -e .`.

### `requirements.txt`
- Adicionar `langgraph-cli[inmem]` (o `langgraph dev`).

### `scripts/studio.sh`
- Sobe `langgraph dev` (porta 2024), checa venv + langgraph-cli + W01 de pé, imprime a URL do Studio.

## Verification

```bash
pip install -e .                       # registra o pacote guardian
bash scripts/studio.sh --no-open       # sobe o servidor
# noutro terminal:
curl -s http://127.0.0.1:2024/ok                                  # {"ok":true}
curl -s -X POST http://127.0.0.1:2024/assistants/search -H 'Content-Type: application/json' -d '{"limit":1}'
# deve listar o assistant 'quality_guardian'. Abra a URL do Studio no navegador.
```
Esperado: o servidor sobe, o grafo `quality_guardian` carrega (10 nós), e o Studio desenha a máquina
de estados interativa. Rode o grafo pela UI e navegue pelos checkpoints (time-travel).

> Narrar: "o mesmo grafo do terminal, agora como produto. Cliquem num nó, vejam o estado. Voltem no
> histórico de checkpoints. É a outra lente sobre a mesma máquina de estados."
