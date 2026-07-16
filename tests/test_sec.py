from datetime import date
from pathlib import Path
from urllib.error import URLError

import pytest

from atlas.evidence import EvidenceKind, SourceRef
from atlas.ingest.sec import SECDataError, SECClient, SECFetchError, parse_capex_observations


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


def test_sec_client_uses_cik_endpoint_and_identifying_user_agent() -> None:
    payload = b'{"facts": {"us-gaap": {}}}'

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return payload

    captured: dict[str, object] = {}

    def opener(request: object, timeout: float) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    client = SECClient(user_agent="Atlas Test <test@example.com>", opener=opener)
    result = client.fetch_company_facts("1")

    assert result["facts"] == {"us-gaap": {}}
    assert "/CIK0000000001.json" in captured["request"].full_url
    assert captured["request"].headers["User-agent"] == "Atlas Test <test@example.com>"
    assert captured["timeout"] == 30.0


def test_sec_client_wraps_transport_errors() -> None:
    def opener(_request: object, timeout: float) -> None:
        raise URLError("offline")

    client = SECClient(user_agent="Atlas Test <test@example.com>", opener=opener)

    with pytest.raises(SECFetchError, match="could not fetch SEC data"):
        client.fetch_company_facts("1")
