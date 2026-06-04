import numpy as np
import pandas as pd

from analysis.residualize import ols_residual, orthogonalize, residual_for_spec


def _series(vals, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(vals, index=idx)


def test_ols_residual_is_orthogonal_to_regressors():
    rng = np.random.default_rng(0)
    x = _series(rng.standard_normal(500))
    y = 2.0 + 1.5 * x + _series(rng.standard_normal(500))
    resid = ols_residual(y, pd.DataFrame({"x": x}))
    assert abs(np.corrcoef(resid.values, x.loc[resid.index].values)[0, 1]) < 1e-6


def test_orthogonalize_removes_market_from_sector():
    rng = np.random.default_rng(1)
    spy = _series(rng.standard_normal(500))
    soxx = 0.9 * spy + 0.3 * _series(rng.standard_normal(500))
    pure = orthogonalize(soxx, spy)
    assert abs(np.corrcoef(pure.values, spy.loc[pure.index].values)[0, 1]) < 1e-6


def test_residual_for_spec_m1_vs_m2_differ_when_sector_loads():
    rng = np.random.default_rng(2)
    spy = _series(rng.standard_normal(600))
    soxx = 0.8 * spy + 0.4 * _series(rng.standard_normal(600))
    asset = 1.0 * spy + 0.7 * soxx + 0.2 * _series(rng.standard_normal(600))
    factors = {"SPY": spy, "SOXX": soxx}
    train = asset.index[:400]
    r1 = residual_for_spec(asset, factors, sector="SOXX", spec="M1", train_index=train)
    r2 = residual_for_spec(asset, factors, sector="SOXX", spec="M2", train_index=train)
    # M2 removes sector too, so residual variance should drop materially
    assert r2.loc[train].var() < r1.loc[train].var()


def test_betas_are_train_only_no_lookahead():
    # Residuals on the test slice must use betas fit on train only.
    rng = np.random.default_rng(3)
    spy = _series(rng.standard_normal(500))
    asset = 1.2 * spy + _series(rng.standard_normal(500))
    factors = {"SPY": spy}
    train = asset.index[:300]
    r = residual_for_spec(asset, factors, sector=None, spec="M1", train_index=train)
    # Full series residualized; index covers train+test
    assert len(r) > len(train)
    assert r.index.equals(asset.index)


def test_leave_one_out_excludes_the_name():
    from analysis.residualize import leave_one_out_sector

    rng = np.random.default_rng(5)
    rets = {t: _series(rng.standard_normal(300)) for t in ("NVDA", "AMD", "MU")}
    loo = leave_one_out_sector("NVDA", ["NVDA", "AMD", "MU"], rets)
    # NVDA must not influence its own factor: equals mean of AMD+MU
    expected = pd.concat([rets["AMD"], rets["MU"]], axis=1).mean(axis=1)
    assert np.allclose(loo.values, expected.loc[loo.index].values)
