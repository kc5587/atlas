from pathlib import Path

import pytest

from atlas.analysis.insights import (
    build_insight,
    load_signal_fixture,
    rank_regions,
)


FIXTURE = Path("data/fixtures/regional_signals.json")


def test_fixture_loader_and_ranking_surface_regional_differences() -> None:
    snapshots = load_signal_fixture(FIXTURE)
    ranked = rank_regions(snapshots)

    assert ranked[0].region_id == "ercot"
    assert ranked[0].pressure == pytest.approx(73.9)
    assert ranked[-1].region_id == "miso"


def test_insight_explains_leading_components_and_caveat() -> None:
    snapshots = load_signal_fixture(FIXTURE)
    miso = next(snapshot for snapshot in snapshots if snapshot.region_id == "miso")

    insight = build_insight(miso.score)

    assert insight.title == "MISO: moderate infrastructure pressure"
    assert "demand pressure" in insight.finding
    assert "execution friction is missing" in insight.caveat


def test_fixture_loader_rejects_unknown_component(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"regions": [{"region_id": "x", "as_of": "2026-07-02", '
        '"signals": {"unknown": {"value": 50, "confidence": 1}}}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown component"):
        load_signal_fixture(path)
