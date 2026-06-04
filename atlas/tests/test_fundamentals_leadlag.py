import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import cycle_control, yoy_growth
from analysis.fundamentals_leadlag import bootstrap_slope_ci, capex_revenue_edge


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
