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
