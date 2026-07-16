from datetime import date

import pytest

from atlas.scoring import ComponentSignal, score_region


AS_OF = date(2026, 7, 2)


def signal(name: str, value: float | None, confidence: float = 1.0) -> ComponentSignal:
    return ComponentSignal(
        name=name,
        value=value,
        confidence=confidence,
        observation_ids=(f"{name}-observation",) if value is not None else (),
    )


def test_score_is_transparent_and_weighted() -> None:
    score = score_region(
        region_id="ercot",
        as_of=AS_OF,
        signals=(
            signal("demand_pressure", 80.0),
            signal("supply_tightness", 60.0),
            signal("price_stress", 40.0),
            signal("execution_friction", 20.0),
        ),
    )

    assert score.pressure == pytest.approx(57.0)
    assert score.confidence == pytest.approx(1.0)
    assert score.missing_components == ()
    assert [component.name for component in score.components] == [
        "demand_pressure",
        "supply_tightness",
        "price_stress",
        "execution_friction",
    ]


def test_missing_component_does_not_become_zero_pressure() -> None:
    score = score_region(
        region_id="pjm",
        as_of=AS_OF,
        signals=(
            signal("demand_pressure", 80.0),
            signal("supply_tightness", 60.0),
            signal("price_stress", 40.0),
            signal("execution_friction", None),
        ),
    )

    assert score.pressure == pytest.approx(63.5294117647)
    assert score.confidence == pytest.approx(0.85)
    assert score.missing_components == ("execution_friction",)


def test_rejects_duplicate_or_out_of_range_signals() -> None:
    with pytest.raises(ValueError, match="duplicate component"):
        score_region(
            region_id="ercot",
            as_of=AS_OF,
            signals=(signal("demand_pressure", 40), signal("demand_pressure", 50)),
        )

    with pytest.raises(ValueError, match="between 0 and 100"):
        score_region(
            region_id="ercot",
            as_of=AS_OF,
            signals=(signal("demand_pressure", 101),),
        )


def test_custom_weights_support_sensitivity_analysis() -> None:
    score = score_region(
        region_id="ercot",
        as_of=AS_OF,
        signals=(
            signal("demand_pressure", 100),
            signal("supply_tightness", 0),
            signal("price_stress", 0),
            signal("execution_friction", None),
        ),
        weights={
            "demand_pressure": 1.0,
            "supply_tightness": 0.0,
            "price_stress": 0.0,
            "execution_friction": 0.0,
        },
    )

    assert score.pressure == 100.0


def test_rejects_invalid_custom_weights() -> None:
    with pytest.raises(ValueError, match="weights must define"):
        score_region("ercot", AS_OF, (signal("demand_pressure", 50),), weights={})
