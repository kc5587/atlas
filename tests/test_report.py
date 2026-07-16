from datetime import date

from atlas.evidence import EvidenceKind, Observation, SourceRef
from atlas.reporting import build_report_export, render_report_html
from atlas.scoring import ComponentSignal, score_region


SOURCE = SourceRef(
    id="fixture:test",
    url="https://example.com/source",
    publisher="Test Publisher",
)


def capex(entity_id: str, value: float, period_end: date, index: int) -> Observation:
    return Observation(
        id=f"capex-{index}",
        metric_id="capex",
        entity_id=entity_id,
        period_start=date(period_end.year, 1, 1),
        period_end=period_end,
        value=value,
        unit="USD",
        source=SOURCE,
        retrieved_at=date(2026, 7, 3),
        vintage=period_end.isoformat(),
        kind=EvidenceKind.OBSERVED,
        quality_flags=("sec_xbrl", "10-K"),
    )


def test_report_contains_unavailable_regions_and_capex_change() -> None:
    score = score_region(
        "ERCO",
        date(2026, 7, 2),
        (
            ComponentSignal("demand_pressure", 80, 1, ("demand-1",)),
            ComponentSignal("supply_tightness", 60, 1, ("supply-1",)),
            ComponentSignal("price_stress", None, 0, ()),
            ComponentSignal("execution_friction", None, 0, ()),
        ),
    )
    observations = (
        capex("cik:0000000001", 100, date(2024, 12, 31), 0),
        capex("cik:0000000001", 150, date(2025, 12, 31), 1),
    )

    report = build_report_export(
        scores=(score,),
        unavailable_regions={"PJM": "no current demand observations"},
        capex_observations=observations,
        company_labels={"cik:0000000001": "Example Cloud"},
        generated_at=date(2026, 7, 3),
        dataset_status="partial",
    )

    assert report["unavailable_regions"][0]["region_id"] == "PJM"
    assert report["companies"][0]["change_vs_prior_pct"] == 50.0
    assert report["execution_evidence"][0]["kind"] == "estimated"
    html = render_report_html(report)
    assert "Example Cloud" in html
    assert "no current demand observations" in html
    assert "observed" in html
    assert "estimated" in html
    assert "inferred" in html
    assert "Regional detail cards" in html
    assert "ERCO" in html
    assert "IEA Energy and AI" in html
