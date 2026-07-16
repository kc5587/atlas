.PHONY: setup test refresh report fixture-report

PYTHONPATH := src
PYTEST ?= pytest
SNAPSHOT_START ?= 2025-07-01
SNAPSHOT_END ?= 2026-07-01
SNAPSHOT_DIR ?= data/snapshots
WHOLESALE_PRICE_CSV ?=

setup:
	uv sync --dev

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST)

refresh:
	PYTHONPATH=$(PYTHONPATH) python3 scripts/refresh_snapshot.py \
		--start $(SNAPSHOT_START) --end $(SNAPSHOT_END) --output-dir $(SNAPSHOT_DIR) \
		$(if $(WHOLESALE_PRICE_CSV),--wholesale-price-csv $(WHOLESALE_PRICE_CSV),)

report:
	PYTHONPATH=$(PYTHONPATH) python3 scripts/generate_report.py \
		--snapshots-root $(SNAPSHOT_DIR)

fixture-report:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/test_refresh.py tests/test_report.py
	root=$$(mktemp -d /tmp/atlas-fixture.XXXXXX); \
	PYTHONPATH=$(PYTHONPATH) python3 scripts/build_fixture_snapshot.py \
		--output-dir $$root; \
	PYTHONPATH=$(PYTHONPATH) python3 scripts/generate_report.py \
		--snapshot-dir $$root/fixture --output-dir $$root/report
