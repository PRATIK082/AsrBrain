.PHONY: install ingest index api ui test eval docker-minimal docker-standard docker-full \
        graph-build graph-stats graph-query tools workflows mindmap agent

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

# ---------------------------------------------------------------- GraphRAG
# CODE_DIRS may point at a folder with C sources / tests (repeat with space).
#   make graph-build CODE_DIRS="src ../some_autosar_code"
graph-build:
	python -m src.graphrag --canonical $(or $(CANONICAL_DB),data/canonical/canonical.db) --out $(or $(GRAPH_DB),data/graph/graph.db) $(foreach d,$(CODE_DIRS),--code-dir $(d))

graph-stats:
	python -m src.tools.cli call graph.stats

graph-query:
	python -m src.tools.cli call graph.search query="$(QUERY)" mode=$(or $(MODE),hybrid) depth=$(or $(DEPTH),2)

tools:
	python -m src.tools.cli list

workflows:
	python -m src.tools.cli workflows

mindmap:
	python -m src.tools.cli mindmap "$(or $(TOPIC),CanIf)" --source $(or $(SOURCE),auto) --depth $(or $(DEPTHTH),2)

agent:
	python -m src.tools.cli agent "$(QUERY)" --workflow $(or $(WORKFLOW),auto) --provider $(or $(PROVIDER),none)

docker-minimal:
	docker compose --profile minimal up --build

docker-standard:
	docker compose --profile standard up --build

docker-full:
	docker compose --profile full up --build
