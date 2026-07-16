from datetime import date

import pytest

from atlas.evidence import EvidenceKind, Observation, SourceRef


def source() -> SourceRef:
    return SourceRef(
        id="eia:grid-monitor",
        url="https://www.eia.gov/electricity/gridmonitor/about",
        publisher="U.S. Energy Information Administration",
    )


def test_observation_preserves_auditable_provenance() -> None:
    observation = Observation(
        id="ercot-demand-2026-07-01",
        metric_id="demand_mw",
        entity_id="ercot",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 1),
        value=82_500.0,
        unit="MW",
        source=source(),
        retrieved_at=date(2026, 7, 2),
        vintage="2026-07-02",
        kind=EvidenceKind.OBSERVED,
        quality_flags=("hourly_aggregate",),
    )

    assert observation.value == 82_500.0
    assert observation.source.publisher == "U.S. Energy Information Administration"
    assert observation.kind is EvidenceKind.OBSERVED


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_observation_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        Observation(
            id="bad",
            metric_id="demand_mw",
            entity_id="ercot",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 1),
            value=value,
            unit="MW",
            source=source(),
            retrieved_at=date(2026, 7, 2),
            vintage="2026-07-02",
            kind=EvidenceKind.OBSERVED,
        )


def test_observation_rejects_reversed_period() -> None:
    with pytest.raises(ValueError, match="period_start"):
        Observation(
            id="bad-period",
            metric_id="demand_mw",
            entity_id="ercot",
            period_start=date(2026, 7, 2),
            period_end=date(2026, 7, 1),
            value=82_500.0,
            unit="MW",
            source=source(),
            retrieved_at=date(2026, 7, 2),
            vintage="2026-07-02",
            kind=EvidenceKind.OBSERVED,
        )
