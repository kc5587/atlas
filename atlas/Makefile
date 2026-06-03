.PHONY: setup ingest build analyze all test lint web-data web-dev web-build

setup:
	uv venv && uv pip install -e ".[dev]"

ingest:
	python -m ingest.prices && python -m ingest.macro && python -m ingest.graph

build:
	cd dbt_project && dbt deps && dbt build --profiles-dir .

analyze:
	python -m analysis.leadlag

all: ingest build analyze

web-data:
	python web/export_data.py --db data/atlas.duckdb --out web/static/data

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

test:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .
