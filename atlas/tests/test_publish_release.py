import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_release import ROW_COUNT_TABLES  # noqa: E402


def test_release_manifest_counts_fundamentals_tables():
    assert "stg_fundamentals" in ROW_COUNT_TABLES
    assert "fundamentals_quarterly" in ROW_COUNT_TABLES


def test_iv_snapshots_in_row_count_tables():
    assert "iv_snapshots" in ROW_COUNT_TABLES
