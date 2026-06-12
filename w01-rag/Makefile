.PHONY: up down logs restart status ingest serve query test test-integration test-all

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose down && docker compose up -d

status:
	docker compose ps

ingest:
	python -m src.ingestion.run

serve:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

query:
	@read -p "Question: " q; \
	curl -s -X POST http://localhost:8000/api/v1/query \
		-H "Content-Type: application/json" \
		-d "{\"question\": \"$$q\"}" | python -m json.tool

test:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v -m integration --timeout=120

test-all:
	pytest tests/ -v -m "" --timeout=120
