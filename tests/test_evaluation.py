from datetime import date, timedelta

from atlas.analysis.demand import DemandPressureConfig
from atlas.analysis.evaluation import EvaluationConfig, run_backtest, run_sensitivity
from atlas.analysis.price import PriceStressConfig
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef(
    id="fixture:evaluation",
    url="https://example.com/evaluation",
    publisher="Test Publisher",
)


def observations(days: int = 140) -> tuple[Observation, ...]:
    start = date(2024, 1, 1)
    rows: list[Observation] = []
    for index in range(days):
        day = start + timedelta(days=index)
        for region, multiplier in (("ERCO", 1.0), ("PJM", 1.1)):
            rows.extend(
                (
                    _observation("demand", region, day, 100 * multiplier + index * multiplier, index, "MW"),
                    _observation("net_generation", region, day, 120 * multiplier, index, "MW"),
                    _observation("wholesale_price", region, day, 20 + index * 0.1, index, "USD_per_MWh"),
                )
            )
    return tuple(rows)


def _observation(
    metric: str, region: str, day: date, value: float, index: int, unit: str
) -> Observation:
    return Observation(
        id=f"{metric}-{region}-{index}",
        metric_id=metric,
        entity_id=region,
        period_start=day,
        period_end=day,
        value=value,
        unit=unit,
        source=SOURCE,
        retrieved_at=day,
        vintage=day.isoformat(),
        kind=EvidenceKind.OBSERVED,
    )


def config() -> EvaluationConfig:
    return EvaluationConfig(
        demand_config=DemandPressureConfig(baseline_days=14, min_baseline_days=7),
        price_config=PriceStressConfig(baseline_days=30, min_baseline_days=10),
        minimum_history_days=30,
    )


def test_backtest_emits_forward_only_rows_and_summary() -> None:
    result = run_backtest(
        observations(),
        ("ERCO", "PJM"),
        (date(2024, 3, 31),),
        horizons=(30,),
        config=config(),
    )

    assert result["lookahead_safe"] is True
    assert len(result["rows"]) == 2
    assert result["summaries"][0]["horizon_days"] == 30


def test_sensitivity_reports_scenario_range() -> None:
    result = run_sensitivity(
        observations(),
        ("ERCO", "PJM"),
        date(2024, 4, 30),
        demand_windows=(14,),
        price_windows=(30,),
    )

    assert result["scenario_count"] == 3
    assert result["region_summary"][0]["scenario_count"] == 3
