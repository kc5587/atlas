import numpy as np

from analysis.significance import auto_block_length


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
