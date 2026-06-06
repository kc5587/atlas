def test_config_track2_constants():
    import config

    # leading-indicator FRED ids are present in FRED_SERIES and in LEADING_INDICATORS
    for sid in ("XTEXVA01KRM664S", "IPG3344S", "CAPUTLG3344S", "PCU334413334413", "A34SNO"):
        assert sid in config.FRED_SERIES
        assert sid in config.LEADING_INDICATORS
    assert config.SEMIS_REVENUE_NAMES == ["AMAT", "LRCX", "NVDA", "AMD", "AVGO", "MU"]
    assert config.H8_LEAD_QUARTERS == (1, 2)
    assert config.H4_HORIZON_MONTHS == (1, 2, 3)
    # every indicator has a publication lag (months)
    for sid in config.LEADING_INDICATORS:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1
