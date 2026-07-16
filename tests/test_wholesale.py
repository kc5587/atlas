from datetime import date
from pathlib import Path

import pytest

from atlas.evidence import EvidenceKind, SourceRef
from atlas.ingest.wholesale import WholesaleDataError, parse_wholesale_csv


FIXTURE = Path("data/fixtures/eia_wholesale.csv")
SOURCE = SourceRef(
    id="eia:wholesale",
    url="https://www.eia.gov/electricity/wholesale/",
    publisher="U.S. Energy Information Administration",
)


def test_wholesale_parser_maps_hubs_to_regions() -> None:
    observations = parse_wholesale_csv(
        FIXTURE,
        source=SOURCE,
        retrieved_at=date(2026, 7, 3),
    )

    assert len(observations) == 2
    assert observations[0].entity_id == "ERCO"
    assert observations[0].metric_id == "wholesale_price"
    assert observations[0].value == 92.5
    assert observations[0].kind is EvidenceKind.OBSERVED


def test_wholesale_parser_rejects_files_without_supported_rows(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("Date,Hub,High Price\n2026-07-02,Unknown Hub,10\n", encoding="utf-8")

    with pytest.raises(WholesaleDataError, match="no supported wholesale rows"):
        parse_wholesale_csv(path, source=SOURCE, retrieved_at=date(2026, 7, 3))
