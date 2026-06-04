from config import H5_FORWARD_HORIZONS


def test_horizons_are_one_and_two_quarters():
    assert H5_FORWARD_HORIZONS == (63, 126)
