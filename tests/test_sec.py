from datetime import date
from pathlib import Path

import pytest

from atlas.evidence import EvidenceKind, SourceRef
from atlas.ingest.sec import SECDataError, parse_capex_observations


FIXTURE = Path("data/fixtures/sec_companyfacts.json")
SOURCE = SourceRef(
    id="sec:companyfacts",
    url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    publisher="U.S. Securities and Exchange Commission",
)


def test_parser_extracts_positive_capex_with_filing_vintage() -> None:
    observations = parse_capex_observations(
        FIXTURE,
        cik="0000000001",
        source=SOURCE,
        retrieved_at=date(2026, 7, 3),
    )

    assert len(observations) == 2
    assert observations[-1].value == 1_200_000_000.0
    assert observations[-1].unit == "USD"
    assert observations[-1].kind is EvidenceKind.OBSERVED
    assert observations[-1].vintage == "2026-02-01"
    assert "sec_xbrl" in observations[-1].quality_flags


def test_parser_rejects_companyfacts_without_capex() -> None:
    with pytest.raises(SECDataError, match="no supported capex fact"):
        parse_capex_observations(
            {"facts": {"us-gaap": {}}},
            cik="0000000001",
            source=SOURCE,
            retrieved_at=date(2026, 7, 3),
        )
