import numpy as np

from analysis.significance import auto_block_length
from analysis.significance import (
    block_resample_one,
    circular_rotate,
    selection_aware,
)


def test_block_length_grows_with_autocorrelation():
    rng = np.random.default_rng(0)
    white = rng.standard_normal(2000)
    # AR(1) with strong persistence
    ar = np.zeros(2000)
    for t in range(1, 2000):
        ar[t] = 0.8 * ar[t - 1] + rng.standard_normal()
    b_white = auto_block_length(white)
    b_ar = auto_block_length(ar)
    assert 1 <= b_white < b_ar
    assert b_ar <= len(ar) // 3


def test_block_length_handles_degenerate_input():
    assert auto_block_length(np.ones(50)) >= 1          # zero variance
    assert auto_block_length(np.array([1.0, 2.0])) >= 1  # too short


def test_circular_rotate_preserves_values_and_length():
    y = np.arange(10.0)
    r = circular_rotate(y, 3)
    assert len(r) == 10
    assert sorted(r) == sorted(y)
    assert r[3] == y[0]


def test_block_resample_preserves_length_and_membership():
    rng = np.random.default_rng(1)
    y = np.arange(100.0)
    r = block_resample_one(y, block=10, rng=rng)
    assert len(r) == 100
    assert set(r).issubset(set(y))


def test_real_lead_lag_is_significant_in_correct_direction():
    rng = np.random.default_rng(2)
    n = 1500
    left = rng.standard_normal(n)
    right = np.empty(n)              # right_t = left_{t-3} + noise  => left leads by 3
    right[:3] = rng.standard_normal(3)
    right[3:] = left[:-3] + 0.5 * rng.standard_normal(n - 3)
    out = selection_aware(left, right, lag_min=1, lag_max=20, iters=500, seed=7)
    assert out["lag"] == 3
    assert out["corr"] > 0
    assert out["p_selection"] < 0.05
    assert out["contradicts_thesis"] is False
    assert out["inverse_lead"] is False


def test_downstream_leads_is_flagged_contradicts_thesis():
    rng = np.random.default_rng(3)
    n = 1500
    right = rng.standard_normal(n)
    left = np.empty(n)               # left_t = right_{t-3}  => right leads (wrong direction)
    left[:3] = rng.standard_normal(3)
    left[3:] = right[:-3] + 0.5 * rng.standard_normal(n - 3)
    out = selection_aware(left, right, lag_min=1, lag_max=20, iters=500, seed=7)
    assert out["contradicts_thesis"] is True


def test_null_cross_corr_centered_on_zero():
    rng = np.random.default_rng(4)
    a = rng.standard_normal(1000)
    b = rng.standard_normal(1000)    # independent
    out = selection_aware(a, b, lag_min=1, lag_max=20, iters=800, seed=1)
    assert out["p_selection"] > 0.1  # nothing real => not significant
