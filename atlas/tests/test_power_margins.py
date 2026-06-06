def test_config_track3_constants():
    import config

    for sid in ("WPU0543", "IPG2211A2N"):
        assert sid in config.FRED_SERIES
    assert config.POWER_NAMES == ["VST", "NRG", "CEG", "ETN", "VRT", "D"]
    assert config.POWER_PRICE_SERIES == ("WPU0543",)
    assert config.POWER_DEMAND_SERIES == ("IPG2211A2N",)
    assert config.H9_LEAD_QUARTERS == (0, 1, 2)
    assert config.H10_HORIZON_MONTHS == (1, 2, 3)
    for sid in config.POWER_PRICE_SERIES + config.POWER_DEMAND_SERIES:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1
