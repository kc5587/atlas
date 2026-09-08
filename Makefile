.PHONY: setup lint test coverage check refresh report fixture-report validation

PYTHONPATH := src
PYTHON ?= uv run python
PYTEST ?= uv run pytest
SNAPSHOT_START ?= 2022-01-01
SNAPSHOT_END ?= 2025-12-31
SNAPSHOT_DIR ?= data/snapshots
WHOLESALE_PRICE_CSV ?=

setup:
	uv sync --locked --dev

lint:
	uv run ruff check src scripts tests
	uv run ruff format --check src scripts tests

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST)

coverage:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) --cov=atlas --cov-report=term-missing

check: lint coverage fixture-report

refresh:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/refresh_snapshot.py \
		--start $(SNAPSHOT_START) --end $(SNAPSHOT_END) --output-dir $(SNAPSHOT_DIR) \
		$(if $(WHOLESALE_PRICE_CSV),--wholesale-price-csv $(WHOLESALE_PRICE_CSV),)

report:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_report.py \
		--snapshots-root $(SNAPSHOT_DIR)

fixture-report:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/test_refresh.py tests/test_report.py
	root=$$(mktemp -d /tmp/atlas-fixture.XXXXXX); \
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_fixture_snapshot.py \
		--output-dir $$root/snapshots; \
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_fixture_report.py \
		--output-dir $$root/report

validation:
	@test -n "$(LIVE_SNAPSHOT)" || (echo "LIVE_SNAPSHOT is required"; exit 1)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_validation.py \
		--snapshot-dir $(LIVE_SNAPSHOT) --output-dir $(VALIDATION_OUTPUT) \
		$(if $(BENCHMARK_JSON),--benchmark-json $(BENCHMARK_JSON),)
