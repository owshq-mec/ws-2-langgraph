# Prompt 10 — UI Chainlit (interface conversacional)

## Context

A peça final: uma cara conversacional pro agente, igual o ShopAgent do W01 tinha Chainlit. O aluno
digita "validar", vê os passos do grafo em tempo real, o health score, e — se der RED — **botões de
Aprovar/Override** (o human-in-the-loop agora visual, não na CLI).

> Encerramento do workshop: do primeiro nó até uma UI onde qualquer pessoa do negócio dispara a
> validação e decide sobre os REDs. "Do zero a uma ferramenta que o C-level usa."

## Objective

Criar `chainlit_app.py` na raiz do projeto.

## Requirements

- `@cl.on_chat_start`: mensagem de boas-vindas explicando o agente; instrui digitar "validar".
- `@cl.on_message`: dentro de `cl.Step(name="Quality Guardian (LangGraph)")`, chama
  `await cl.make_async(run_guardian)(dataset="customers", thread_id=<session id>)`; depois `_present`.
- `_present(result, thread_id)`:
  - mostra os passos do grafo (`steps`).
  - se `status == "paused"`: mostra o payload do interrupt (pergunta + violações) e DUAS `cl.Action`
    ("approve" e "override") com payload `{thread_id, decision}`.
  - se `completed`: mostra flag com emoji (🟢/🟡/🔴), rows, health, n_red.
- `@cl.action_callback("approve")` e `("override")`: chamam `cl.make_async(resume_guardian)(thread_id, decision)`
  e re-apresentam o resultado.

## Verification

```bash
chainlit run chainlit_app.py -w        # abre no browser (localhost:8000)
# digitar "validar" → ver os passos do grafo + resultado.
# (forçar um RED no Postgres antes p/ ver o HITL com botões.)
```
A UI deve rodar o agente, mostrar os passos, e — em caso de RED — oferecer os botões de decisão.
Demo de encerramento: validar → RED → clicar Aprovar → ver gravar no Ledger.
