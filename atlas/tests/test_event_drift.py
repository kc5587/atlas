from config import H2_DRIFT_HORIZONS, H2_SURPRISE_K


def test_h2_config():
    assert H2_DRIFT_HORIZONS == (21, 42, 63)
    assert H2_SURPRISE_K == 4
