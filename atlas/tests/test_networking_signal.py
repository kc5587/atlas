import pandas as pd

from analysis.networking_signal import networking_capex_edges

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
