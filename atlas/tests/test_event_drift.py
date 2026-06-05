from config import H2_DRIFT_HORIZONS, H2_SURPRISE_K

import numpy as np
import pandas as pd
from analysis.event_drift import capex_surprise


def test_h2_config():
    assert H2_DRIFT_HORIZONS == (21, 42, 63)
    assert H2_SURPRISE_K == 4


def _fund(ticker, n=24, start="2016-03-31"):
    pe = pd.date_range(start, periods=n, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    rng = np.random.default_rng(0)
    capex = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    return pd.DataFrame({"ticker": ticker, "period_end": pe, "filed": filed, "capex": capex})


def test_capex_surprise_is_standardized_and_filing_indexed():
    s = capex_surprise(_fund("U"), "U", k=4)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert abs(s.mean()) < 1.0 and 0.3 < s.std() < 3.0
    f2 = _fund("U")
    base = capex_surprise(f2, "U", k=4)
    f2.loc[f2.index[-1], "capex"] *= 5
    after = capex_surprise(f2, "U", k=4)
    assert np.allclose(base.iloc[:-1].to_numpy(), after.iloc[:-1].to_numpy())
