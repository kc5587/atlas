from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from atlas.evidence import EvidenceKind, SourceRef
from atlas.ingest.eia import EIADataError, parse_hourly_demand


FIXTURE = Path("data/fixtures/eia_hourly_demand.json")
SOURCE = SourceRef(
    id="eia:grid-monitor",
    url="https://www.eia.gov/electricity/gridmonitor/about",
    publisher="U.S. Energy Information Administration",
)


def test_parser_creates_timestamped_observations_and_skips_other_series() -> None:
    observations = parse_hourly_demand(
        FIXTURE,
        source=SOURCE,
        retrieved_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )

    assert len(observations) == 2
    assert observations[0].entity_id == "ERCO"
    assert observations[0].period_start == datetime(2026, 7, 2, 0, tzinfo=timezone.utc)
    assert observations[0].value == 82_500.0
    assert observations[0].kind is EvidenceKind.OBSERVED
    assert observations[0].retrieved_at == datetime(2026, 7, 3, tzinfo=timezone.utc)


def test_parser_rejects_rows_with_invalid_values() -> None:
    with pytest.raises(EIADataError, match="invalid demand value"):
        parse_hourly_demand(
            {
                "response": {
                    "data": [
                        {
                            "period": "2026-07-02T00:00:00Z",
                            "respondent": "ERCO",
                            "type-name": "Demand",
                            "value": "bad",
                        }
                    ]
                }
            },
            source=SOURCE,
            retrieved_at=date(2026, 7, 3),
        )


def test_parser_rejects_missing_data_rows() -> None:
    with pytest.raises(EIADataError, match="no hourly demand rows"):
        parse_hourly_demand(
            {"response": {"data": []}},
            source=SOURCE,
            retrieved_at=date(2026, 7, 3),
        )
