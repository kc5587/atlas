from config import H5_FORWARD_HORIZONS

import numpy as np
import pandas as pd
from analysis.capex_price import capex_growth_at_filed, forward_excess_return


def test_horizons_are_one_and_two_quarters():
    assert H5_FORWARD_HORIZONS == (63, 126)


def _daily(start, n, vals):
    return pd.Series(vals, index=pd.bdate_range(start, periods=n))


def test_forward_excess_return_starts_strictly_after_filed():
    # Flat in train (alpha≈0), positive drift AFTER filed -> forward residual > 0.
    # (M2 residual subtracts fitted alpha, so a constant-everywhere series → ~0.)
    idx = pd.bdate_range("2020-01-01", periods=400)
    vals = np.where(np.arange(400) <= 100, 0.0, 0.001)
    asset = pd.Series(vals, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    filed = idx[100]
    r = forward_excess_return(asset, factors, sector="SOXX", filed=filed, horizon_days=63)
    assert r > 0
    assert abs(r - 0.063) < 0.01


def test_forward_excess_return_nan_when_no_future_data():
    idx = pd.bdate_range("2020-01-01", periods=100)
    asset = pd.Series(0.001, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    r = forward_excess_return(asset, factors, sector="SOXX", filed=idx[-1], horizon_days=63)
    assert np.isnan(r)


def test_capex_growth_indexed_by_filed_date():
    pe = pd.date_range("2018-03-31", periods=12, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    fund = pd.DataFrame(
        {"ticker": "U", "period_end": pe, "filed": filed, "capex": np.linspace(100, 210, 12)}
    )
    g = capex_growth_at_filed(fund, "U")
    assert len(g) == 8
    assert (g.index == pd.DatetimeIndex(filed[4:])).all()
