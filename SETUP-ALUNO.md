# Setup do Aluno — W02 (Quality Guardian)

> O que fazer **depois de clonar o repositório** e **antes da aula**. ~15 min.
> Ao fim, você tem o W01 (o cérebro) rodando e o scaffold do agente pronto pra construir ao vivo.

## Pré-requisitos

- **OrbStack** (recomendado, Mac) ou **Docker Desktop** — instalado e aberto.
- **Python 3.11+** (`python3 --version`).
- **Claude Code** instalado (`claude --version`) — é com ele que você constrói o agente na aula.
- (Opcional) uma `ANTHROPIC_API_KEY` — sem ela o agente roda igual (fallback determinístico).

## Passo 1 — Subir o W01 (o cérebro que o agente consome)

> Um comando. Sobe Postgres/Qdrant/Neo4j/Mongo/SeaweedFS + um gerador de dados vivo.

```bash
cd workshop/w02-langgraph
bash scripts/bootstrap-w01.sh
```

Espere o banner verde **"✓ W01 PRONTO"**. Confirme:
```bash
docker ps | grep dataops          # 6 containers "dataops-*" (Up/healthy)
```

> Porta do Postgres no host: **5442**. Se algo falhar, rode o script de novo (é idempotente).

## Passo 2 — Preparar o scaffold do agente

> Você vai **construir** o agente do zero na aula (colando os prompts no Claude Code). Aqui só
> prepara o ambiente: o `src/guardian/` começa **vazio** — é o que você vai preencher.

```bash
cd aluno
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # opcional: edite e ponha sua ANTHROPIC_API_KEY
```

Confirme que as dependências entraram:
```bash
python -c "import langgraph, langchain, psycopg, rich; print('OK')"
```

## Passo 3 — Abrir o Claude Code no scaffold

```bash
# de dentro de aluno/
claude
```

Na aula, o instrutor vai te guiar a colar os prompts de `prompts/` (na ordem: 1, 2, 3, …) no Claude
Code. Cada prompt gera uma parte do agente. Você vai **ver o código nascer** e rodar.

## Pronto!

Quando o `bootstrap-w01.sh` terminar verde e o `python -c "import ..."` imprimir `OK`, você está
pronto. Na aula, é só seguir o instrutor colando os prompts.

---

### Estrutura do que você clonou

| Pasta/arquivo | O que é |
|---|---|
| `aluno/` | **Seu** ponto de partida: `src/guardian/` vazio + prompts + requirements. Você constrói aqui. |
| `aluno/prompts/` | Os prompts que você cola no Claude Code (na ordem). |
| `scripts/` | `bootstrap-w01` (sobe o W01), `seed-red`/`seed-yellow`/`restore` (gatilhos de demo), `studio` (LangGraph Studio). |
| `w01-rag/` | O W01 (o cérebro). Você não mexe aqui — só sobe com o bootstrap. |

> O **gabarito** (agente pronto) fica com o instrutor — o objetivo é VOCÊ construir do zero na aula.
> Se travar, o instrutor te ajuda com o trecho certo.

### Problemas comuns

| Sintoma | Solução |
|---|---|
| `docker: command not found` | Instale o OrbStack ou Docker Desktop e abra antes de rodar o bootstrap. |
| bootstrap trava esperando saúde | Rode de novo (`bash scripts/bootstrap-w01.sh`). Neo4j demora ~30s. |
| `ModuleNotFoundError` ao importar | Ative o venv: `. .venv/bin/activate` e `pip install -r requirements.txt`. |
| porta 5442 ocupada | Pare outros Postgres locais, ou veja `scripts/bootstrap-w01.sh` (porta remapeável). |
