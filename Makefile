.PHONY: install ingest index api ui test eval eval-build eval-run eval-holdout eval-gate \
        eval-review eval-coverage eval-fixture golden-review docker-minimal docker-standard docker-full

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

# --- evaluation harness (a PR that regresses a headline metric beyond tolerance fails) ---
# Windows has no `make`; run the commands under each target directly.

# Build the golden set (350+ items) and freeze the hold-out split.
eval-build:
	python -m src.evaluation.build --canonical data/canonical/canonical.db

# Retrieval-only run over the whole golden set: fast and deterministic.
eval-run:
	python -m src.evaluation.cli run --mode retrieval --label retrieval

# End-to-end run with the LLM over a stratified sample.
eval-full:
	python -m src.evaluation.cli run --mode full --llm-sample 40 --label full

# Score the frozen hold-out split only (never tune on it).
eval-holdout:
	python -m src.evaluation.cli run --mode retrieval --split-name holdout --label holdout

# Fail when a headline metric regresses beyond the agreed tolerance.
eval-gate:
	python -m src.evaluation.gate --run reports/evaluation/latest.json --gate data/benchmarks/eval_gate.json

# Export the stratified sample for expert review.
eval-review:
	python -m src.evaluation.cli review --out data/benchmarks/expert_review_v2.csv

# Show the realised coverage mix against the §9 targets.
eval-coverage:
	python -m src.evaluation.cli coverage

# Synthetic corpus used by the CI gate: no AUTOSAR PDF, no LLM, seconds to build.
eval-fixture:
	python -m src.evaluation.fixture --out data/canonical/fixture.db
	python -m src.indexing.build --canonical data/canonical/fixture.db --out data/indexes/fixture
	python -m src.evaluation.build --canonical data/canonical/fixture.db --golden data/benchmarks/fixture_golden.jsonl --split data/benchmarks/fixture_holdout.json --review reports/evaluation/fixture_review.csv
	python -m src.evaluation.cli run --golden data/benchmarks/fixture_golden.jsonl --split data/benchmarks/fixture_holdout.json --canonical data/canonical/fixture.db --index data/indexes/fixture --out reports/evaluation/fixture --mode retrieval --label ci-fixture
	python -m src.evaluation.gate --run reports/evaluation/fixture/latest.json --gate data/benchmarks/eval_gate_ci.json --report reports/evaluation/fixture/gate.json

# Legacy v1 runner (regenerates reports/evaluation/validated.json on demand; run
# artefacts are not stored in git).
eval-legacy:
	python -m src.evaluation.run --benchmark data/benchmarks/autosar_benchmark_v1.jsonl --out reports/evaluation/validated.json

docker-minimal:
	docker compose --profile minimal up --build

docker-standard:
	docker compose --profile standard up --build

docker-full:
	docker compose --profile full up --build
