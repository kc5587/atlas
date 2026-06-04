from config import FACTOR_TICKERS, LAG_MAX, LAG_MIN, STAGE_SECTOR


def test_factor_tickers_distinct_from_universe():
    from config import UNIVERSE

    assert set(FACTOR_TICKERS.values()).isdisjoint(set(UNIVERSE))
    assert FACTOR_TICKERS["market"] == "SPY"


def test_every_stage_maps_to_a_sector_factor():
    for stage in ("equipment", "foundry", "chips", "cloud"):
        assert STAGE_SECTOR[stage] in FACTOR_TICKERS


def test_lag_domain_is_one_sided():
    assert LAG_MIN == 1
    assert LAG_MAX >= LAG_MIN
