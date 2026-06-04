import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import cycle_control, yoy_growth


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
