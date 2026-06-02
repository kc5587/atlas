.PHONY: setup ingest build analyze app all test lint

setup:
	uv venv && uv pip install -e ".[dev]"

ingest:
	python -m ingest.prices && python -m ingest.macro && python -m ingest.graph

build:
	cd dbt_project && dbt deps && dbt build --profiles-dir .

analyze:
	python -m analysis.leadlag

app:
	streamlit run app/streamlit_app.py

all: ingest build analyze

test:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .
