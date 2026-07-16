from datetime import date
from urllib.parse import parse_qs, urlparse
from urllib.error import URLError

import pytest

from atlas.ingest.eia import (
    EIAFetchError,
    EIAHourlyQuery,
    EIAClient,
    build_hourly_query_url,
)


def test_query_url_is_explicit_and_repeatable() -> None:
    query = EIAHourlyQuery(
        regions=("ERCO", "PJM"),
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
        api_key="test-key",
    )

    parsed = parse_qs(urlparse(build_hourly_query_url(query)).query)

    assert parsed["facets[respondent][]"] == ["ERCO", "PJM"]
    assert parsed["frequency"] == ["hourly"]
    assert parsed["api_key"] == ["test-key"]
    assert parsed["start"] == ["2026-07-01"]
    assert parsed["end"] == ["2026-07-02"]


def test_client_parses_payload_through_injected_transport() -> None:
    payload = (
        b'{"response": {"data": [{"period": "2026-07-02T00:00:00Z", '
        b'"respondent": "ERCO", "type-name": "Demand", "value": "82500", '
        b'"value-units": "MW"}]}}'
    )

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

    client = EIAClient(api_key="test-key", opener=opener)
    observations = client.fetch_hourly_demand(
        EIAHourlyQuery(regions=("ERCO",), start=date(2026, 7, 2), end=date(2026, 7, 2))
    )

    assert observations[0].value == 82_500.0
    assert captured["timeout"] == 30.0
    assert "Atlas/" in captured["request"].headers["User-agent"]


def test_client_wraps_transport_errors() -> None:
    def opener(_request: object, timeout: float) -> None:
        raise URLError("offline")

    client = EIAClient(opener=opener)

    with pytest.raises(EIAFetchError, match="could not fetch EIA data"):
        client.fetch_hourly_demand(
            EIAHourlyQuery(regions=("ERCO",), start=date(2026, 7, 2), end=date(2026, 7, 2))
        )
