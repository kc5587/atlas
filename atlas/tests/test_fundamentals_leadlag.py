import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import cycle_control, yoy_growth
from analysis.fundamentals_leadlag import (
    bootstrap_slope_ci,
    capex_revenue_edge,
    capex_revenue_edges,
)


def _q(vals, start="2015-03-31"):
    idx = pd.date_range(start, periods=len(vals), freq="QE")
    return pd.Series(vals, index=idx)


def test_yoy_growth_is_four_quarter_log_diff():
    s = _q([100, 110, 120, 130, 200, 220, 240, 260])  # year 2 = 2x year 1
    g = yoy_growth(s)
    assert len(g) == 4                      # first 4 dropped
    np.testing.assert_allclose(g.iloc[0], np.log(200 / 100), rtol=1e-9)


def test_cycle_control_residual_orthogonal_to_factor():
    rng = np.random.default_rng(0)
    cycle = _q(rng.standard_normal(30))
    target = 1.5 * cycle + _q(rng.standard_normal(30))
    resid = cycle_control(target, cycle)
    aligned = pd.concat([resid.rename("r"), cycle.rename("c")], axis=1, join="inner").dropna()
    assert abs(np.corrcoef(aligned["r"], aligned["c"])[0, 1]) < 1e-6


def test_bootstrap_slope_ci_brackets_true_slope():
    rng = np.random.default_rng(1)
    x = rng.standard_normal(120)
    y = 0.8 * x + 0.2 * rng.standard_normal(120)
    lo, hi, slope = bootstrap_slope_ci(x, y, block=2, iters=400, seed=3)
    assert lo < 0.8 < hi
    assert lo > 0                       # CI excludes 0 for a real relationship


def test_capex_revenue_edge_detects_lead_and_direction():
    rng = np.random.default_rng(2)
    n = 40
    capex_g = _q(rng.standard_normal(n))
    # downstream revenue growth = upstream capex growth lagged 2 quarters
    rev_g = capex_g.shift(2) + 0.3 * _q(rng.standard_normal(n))
    cycle = _q(rng.standard_normal(n))
    out = capex_revenue_edge(capex_g, rev_g, cycle, lag_min=1, lag_max=4,
                             iters=300, seed=5)
    assert out["lag"] == 2
    assert out["slope"] > 0
    assert out["contradicts_thesis"] is False
    assert out["n_quarters"] > 0


def test_capex_revenue_edges_aligns_offset_fiscal_calendars_between_endpoints():
    """Upstream and downstream report on different fiscal calendars (e.g. NVDA's
    late-July quarter vs MSFT's Sep-30 quarter). They must still align by calendar
    quarter — exact-timestamp joins give 0 quarters (the live-data bug)."""
    import json
    n = 24
    cal = pd.date_range("2016-03-31", periods=n, freq="QE")     # downstream: calendar q-ends
    fis = cal - pd.Timedelta(days=33)                            # upstream: ~1 month earlier, same quarter
    rng = np.random.default_rng(0)
    capex = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    rev = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    peer = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    fundamentals = pd.concat([
        pd.DataFrame({"ticker": "U", "period_end": fis, "capex": capex, "revenue": np.nan}),
        pd.DataFrame({"ticker": "D", "period_end": cal, "capex": np.nan, "revenue": rev}),
        pd.DataFrame({"ticker": "P", "period_end": cal, "capex": np.nan, "revenue": peer}),
    ], ignore_index=True)
    nodes = pd.DataFrame([
        {"id": "u", "tickers": json.dumps(["U"])},
        {"id": "d", "tickers": json.dumps(["D"])},
        {"id": "p", "tickers": json.dumps(["P"])},
    ])
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}])
    out = capex_revenue_edges(fundamentals, nodes, edges, iters=50, seed=1)
    assert len(out) == 1
    assert out["n_quarters"].iloc[0] >= 9      # was 0 with exact-timestamp joins


def test_fdr_family_excludes_degenerate_edges():
    """BH-FDR must be computed over ELIGIBLE edges only; degenerate (no-data)
    edges with p=1 must not inflate q for the real edge."""
    import json
    n = 24
    cal = pd.date_range("2016-03-31", periods=n, freq="QE")
    rng = np.random.default_rng(3)
    capex = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    rev = capex  # strong real relationship for the eligible edge
    peer = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    fundamentals = pd.concat([
        pd.DataFrame({"ticker": "U", "period_end": cal, "capex": capex, "revenue": np.nan}),
        pd.DataFrame({"ticker": "D", "period_end": cal, "capex": np.nan, "revenue": rev}),
        pd.DataFrame({"ticker": "P", "period_end": cal, "capex": np.nan, "revenue": peer}),
        # X has too few capex quarters -> edge x->d is appended but degenerate (NaN slope)
        pd.DataFrame({"ticker": "X", "period_end": cal[:6], "capex": capex[:6], "revenue": np.nan}),
    ], ignore_index=True)
    nodes = pd.DataFrame([
        {"id": "u", "tickers": json.dumps(["U"])},
        {"id": "d", "tickers": json.dumps(["D"])},
        {"id": "p", "tickers": json.dumps(["P"])},
        {"id": "x", "tickers": json.dumps(["X"])},
    ])
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}, {"from_id": "x", "to_id": "d"}])
    out = capex_revenue_edges(fundamentals, nodes, edges, iters=100, seed=2)
    elig = out[out["slope"].notna()]
    degen = out[out["slope"].isna()]
    assert len(elig) == 1 and len(degen) == 1
    # eligible edge's q equals its own p (family size 1), not inflated by the degenerate edge
    assert elig["q_value"].iloc[0] == elig["p_selection"].iloc[0]
    assert degen["q_value"].isna().all()


def test_capex_revenue_edges_handles_staggered_peer_fiscal_calendars():
    periods = pd.date_range("2015-03-31", periods=20, freq="QE")
    shifted = periods + pd.Timedelta(days=31)
    base = np.linspace(100.0, 200.0, len(periods))
    fundamentals = pd.concat([
        pd.DataFrame({"ticker": "UP", "period_end": periods, "capex": base, "revenue": np.nan}),
        pd.DataFrame({"ticker": "DOWN", "period_end": periods, "capex": np.nan, "revenue": np.roll(base, 2)}),
        pd.DataFrame({"ticker": "PEER1", "period_end": periods, "capex": np.nan, "revenue": base * 1.1}),
        pd.DataFrame({"ticker": "PEER2", "period_end": shifted, "capex": np.nan, "revenue": base * 0.9}),
    ], ignore_index=True)
    nodes = pd.DataFrame([
        {"id": "up", "tickers": '["UP"]'},
        {"id": "down", "tickers": '["DOWN"]'},
    ])
    edges = pd.DataFrame([{"from_id": "up", "to_id": "down"}])
    out = capex_revenue_edges(fundamentals, nodes, edges, iters=50, seed=4)
    assert not out.empty
    assert out["n_quarters"].iloc[0] > 0
