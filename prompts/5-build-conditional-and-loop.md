# Prompt 05 — Aresta condicional + evaluator-optimizer (auto-correção REAL)

## Context

O grafo linear sempre faz o mesmo caminho. Agora ensinamos o agente a **decidir** (aresta condicional
= o "roteador" do módulo de Design Patterns, em código) e a **se corrigir** com o padrão
**evaluator-optimizer** (Reflection): um gerador FRACO propõe uma correção, um avaliador FORTE julga.

> A virada didática: não basta um loop que repete o mesmo passo. O loop precisa MUDAR algo a cada
> volta — senão "se corrige" é só retórica. No evaluator-optimizer, o gerador (Haiku, modelo barato)
> propõe correções pros registros fracos; o avaliador (Sonnet, modelo caro) audita. Se aceita e o
> registro re-pontua green, o health SOBE — auto-correção de verdade. Se rejeita, endurece e tenta de
> novo. Se esgota o orçamento, escala pro humano.

> Narrar: ao adicionar os nós, REDESENHE o grafo (`run draw`) — o aluno vê `score → optimize →
> evaluate` e o ciclo de volta. Ao rodar com um yellow forçado, o stream mostra o health subindo.

## Objective

Criar `src/guardian/llm.py` (a camada LLM com fallback) e evoluir `src/guardian/graph.py`:
adicionar os nós `optimize`/`evaluate`/`recommend`, os 2 roteadores, e o ciclo.

## Requirements

### `llm.py` — a camada LLM (LangChain), com FALLBACK determinístico
> Política de robustez: se não há `ANTHROPIC_API_KEY` ou a API falha, cada função cai numa heurística
> determinística. O grafo NUNCA quebra ao vivo. LangChain 1.3: `from langchain.chat_models import
> init_chat_model`. O LLM emite texto; quem decide o fluxo é o grafo. O LLM nunca executa nada.

> **Setup da chave (p/ ver o LLM real, não o fallback):** preencha `ANTHROPIC_API_KEY` no `.env`
> com uma chave **de uma conta com saldo** — a API da Anthropic é pré-paga, **não tem free tier**
> (o plano grátis do claude.ai não dá acesso à API). Sem créditos, a chamada retorna `400 credit
> balance too low`, o `try/except` engole e cai em `fonte="fallback"`. Atenção: `_has_key()` só
> checa se a var existe — uma chave-placeholder ou sem saldo passa no gate mas falha na chamada.
> Para confirmar que o LLM real respondeu, verifique `fonte="llm"` na saída. O `.env` só é lido
> porque o `config.py` chama `load_dotenv()` (prompt 02) — sem isso, criar o `.env` não basta.

- `_has_key()` → bool (checa `ANTHROPIC_API_KEY` no ambiente). `_model(spec)` cacheado
  (`init_chat_model(spec, temperature=0)`).
- `recommend(dataset, health, flag, violations) -> (texto, fonte)`: diagnóstico curto em PT (Sonnet,
  `config.LLM_MODEL`). Fonte = `"llm"` ou `"fallback"`. Fallback: agrupa violações por tipo
  (email/company/orders) e sugere ação por flag.
- `propose_fix(row, hardening=0, feedback="") -> (patch, fonte)`: **gerador FRACO** (Haiku,
  `config.GENERATOR_MODEL`) propõe `{email?, company?, failed_orders?}` p/ um registro fraco. Recebe o
  `feedback` da rejeição anterior (o loop de feedback). Fallback: normaliza email inválido, infere
  company do nome, e remedia `failed_orders→0` (a "ação corretiva" simulada).
- `judge_fix(row, patch) -> (aceita, motivo, fonte)`: **avaliador FORTE** (Sonnet,
  `config.EVALUATOR_MODEL`) julga a proposta. Fallback: aceita se email tem `@` e company não-nula.

### `graph.py` — os nós novos
- `optimize(state)`: pega `_rows`, filtra os fracos (score != green via `scoring.evaluate_row`), chama
  `llm.propose_fix(r, hardening, eval_feedback)` p/ cada um; guarda `proposed_fixes`.
- `evaluate(state)`: p/ cada `(id, patch)`, `llm.judge_fix`; **só aceita se o registro corrigido
  re-pontua green** (`scoring.flag_for(evaluate_row({**row, **patch})) == "green"`). Se todas aceitas →
  `corrected_rows` + `eval_accepted=True`. Se alguma falha → `eval_accepted=False`, `hardening++`,
  `eval_feedback` com o motivo.
- `recommend(state)`: chama `llm.recommend(...)`; guarda `recommendation`. (Roda antes de gravar em
  qualquer caminho.)
- `validate_rules`: na reentrada, usa `corrected_rows` se houver (re-pontua com os corrigidos → health
  sobe). Senão lê o Ledger.

### `graph.py` — os 2 roteadores
- `route_after_decide(state) -> Literal["optimize","human_gate","recommend"]`:
  `red → human_gate` · `yellow and hardening < MAX_RETRIES → optimize` · senão → `recommend`.
- `route_after_evaluate(state) -> Literal["validate_rules","optimize","human_gate"]`:
  `eval_accepted → validate_rules` · `hardening < MAX_RETRIES → optimize` · senão → `human_gate`.

### `graph.py` — as arestas
- `START → check_schema → validate_rules → score`.
- `add_conditional_edges("score", route_after_decide, {"optimize":"optimize",
  "human_gate":"human_gate", "recommend":"recommend"})`.
- `optimize → evaluate`; `add_conditional_edges("evaluate", route_after_evaluate, {...})`.
- `recommend → write_ledger → END`.
- (o `human_gate` ainda é stub que vai a `recommend`; vira `interrupt()` real no prompt 07.)

## Verification

```bash
python -m src.guardian.run draw     # agora: score→optimize→evaluate, loop de volta a validate_rules
# força um yellow e roda o loop:
cd .. && bash scripts/seed-yellow.sh 2 && cd agent
python -m src.guardian.run run --thread yellow-demo
cd .. && bash scripts/restore.sh && cd agent
```
Esperado: o grafo desenha o loop; ao rodar, `score=yellow → optimize → evaluate (ACEITOU) →
validate_rules (health SOBE) → green → recommend → write`. **Auto-correção real: o health sobe.**

> Narrar: "O barato erra, o caro corrige. E tem um teto — `MAX_RETRIES`. Se não resolver, escala pro
> humano. Esse é o evaluator-optimizer costurado ao human-in-the-loop."
