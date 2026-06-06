import numpy as np
import pandas as pd

from analysis.networking_signal import networking_capex_edges, networking_propagation

NODES = pd.DataFrame([
    {"id": "microsoft", "tickers": '["MSFT"]', "stage": "cloud"},
    {"id": "meta", "tickers": '["META"]', "stage": "cloud"},
    {"id": "amazon", "tickers": '["AMZN"]', "stage": "cloud"},
    {"id": "arista", "tickers": '["ANET"]', "stage": "networking"},
    {"id": "marvell", "tickers": '["MRVL"]', "stage": "networking"},
    {"id": "nvidia", "tickers": '["NVDA"]', "stage": "chips"},
])
EDGES = pd.DataFrame([
    {"from_id": "arista", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "arista", "to_id": "meta", "relationship": "supplies"},
    {"from_id": "marvell", "to_id": "amazon", "relationship": "supplies"},
    {"from_id": "marvell", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "nvidia", "to_id": "microsoft", "relationship": "supplies"},  # not networking
])


def test_networking_capex_edges_reverses_and_filters():
    out = networking_capex_edges(NODES, EDGES)
    pairs = set(zip(out["from_id"], out["to_id"]))
    # reversed: customer (cloud) -> supplier (networking)
    assert pairs == {
        ("microsoft", "arista"), ("meta", "arista"),
        ("amazon", "marvell"), ("microsoft", "marvell"),
    }
    # the chips->cloud edge is excluded (not a networking edge)
    assert ("microsoft", "nvidia") not in pairs
    assert ("nvidia", "microsoft") not in pairs


def _fundamentals_fixture():
    # 16 quarters; MSFT capex leads ANET revenue with a clear positive slope.
    qs = pd.period_range("2020Q1", periods=16, freq="Q").to_timestamp()
    msft_capex = np.linspace(10.0, 26.0, 16)
    anet_rev = np.concatenate([[np.nan], np.linspace(5.0, 18.0, 16)[:-1]])  # lag 1
    other_rev = np.linspace(7.0, 9.0, 16)  # flat-ish peer for the cycle factor
    frames = []
    for ticker, col, vals in [("MSFT", "capex", msft_capex),
                              ("ANET", "revenue", anet_rev),
                              ("NVDA", "revenue", other_rev)]:
        df = pd.DataFrame({"ticker": ticker, "period_end": qs,
                           "revenue": np.nan, "capex": np.nan, "gross_margin": np.nan,
                           "filed": qs})
        df[col] = vals
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_networking_propagation_runs_on_reversed_edges():
    fundamentals = _fundamentals_fixture()
    out = networking_propagation(fundamentals, NODES, EDGES, iters=200, seed=0)
    # one row per reversed networking edge that has fundamentals on both sides
    assert ("microsoft", "arista") in set(zip(out["left"], out["right"]))
    assert "slope" in out.columns and "q_value" in out.columns


def test_stage_tickers_collects_tickers_for_a_stage():
    from analysis.leadlag import stage_tickers

    assert stage_tickers(NODES, "networking") == {"ANET", "MRVL"}
    assert stage_tickers(NODES, "cloud") == {"MSFT", "META", "AMZN"}


def test_core_fundamentals_drops_excluded_stage_tickers():
    from analysis.leadlag import core_fundamentals

    fund = pd.DataFrame({
        "ticker": ["ANET", "MRVL", "MSFT", "NVDA"],
        "period_end": pd.Timestamp("2024-01-01"),
        "revenue": 1.0, "capex": 1.0, "gross_margin": 1.0,
    })
    cf = core_fundamentals(fund, NODES, exclude_stages=["networking"])
    assert set(cf["ticker"]) == {"MSFT", "NVDA"}


def test_h1_cycle_pool_is_invariant_to_networking_fundamentals():
    """The core H1 driver must give identical results whether or not networking
    suppliers are present in the raw fundamentals, once routed through
    core_fundamentals. This is the regression guard for the cycle-pool leak."""
    from analysis.fundamentals_leadlag import capex_revenue_edges
    from analysis.leadlag import core_fundamentals

    base = _fundamentals_fixture()  # MSFT, ANET, NVDA
    # A core edge that does NOT touch networking: NVDA(capex) -> MSFT(revenue).
    core_edges = pd.DataFrame([
        {"from_id": "nvidia", "to_id": "microsoft", "relationship": "supplies"},
    ])
    # Add MSFT capex + NVDA capex so the edge is computable, and give ANET a wild
    # revenue series that would distort the leave-one-out cycle factor if leaked.
    base = base.copy()
    base.loc[base["ticker"] == "NVDA", "capex"] = np.linspace(2.0, 9.0, 16)
    base.loc[base["ticker"] == "MSFT", "revenue"] = np.linspace(20.0, 40.0, 16)
    polluted = base.copy()
    polluted.loc[polluted["ticker"] == "ANET", "revenue"] = np.linspace(1.0, 500.0, 16)

    cf_clean = core_fundamentals(base, NODES, exclude_stages=["networking"])
    cf_poll = core_fundamentals(polluted, NODES, exclude_stages=["networking"])
    a = capex_revenue_edges(cf_clean, NODES, core_edges, iters=200, seed=0)
    b = capex_revenue_edges(cf_poll, NODES, core_edges, iters=200, seed=0)
    # Identical: networking revenue never enters the core cycle pool.
    assert a["slope"].iloc[0] == b["slope"].iloc[0]
