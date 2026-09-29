.PHONY: install ingest index api ui test eval docker-minimal docker-standard docker-full

install:
	pip install -r requirements.txt

ingest:
	python -m src.ingestion.pipeline --pdf-dir pdf --out data/canonical

index:
	python -m src.indexing.build --canonical data/canonical/canonical.db

api:
	uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	streamlit run apps/streamlit/app.py

test:
	pytest -q

eval:
	python -m src.evaluation.run --benchmark data/benchmarks/autosar_benchmark_v1.jsonl --out reports/evaluation/validated.json

docker-minimal:
	docker compose --profile minimal up --build

docker-standard:
	docker compose --profile standard up --build

docker-full:
	docker compose --profile full up --build
