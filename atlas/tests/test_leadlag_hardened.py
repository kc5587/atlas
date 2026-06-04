import json

import numpy as np
import pandas as pd

from analysis.leadlag import bh_fdr, build_hardened_edges


def _returns_df():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2012-01-01", periods=1500)
    spy = rng.standard_normal(1500)
    soxx = 0.8 * spy + 0.4 * rng.standard_normal(1500)
    up = 0.5 * spy + 0.6 * soxx + rng.standard_normal(1500)
    down = np.empty(1500)
    down[:3] = rng.standard_normal(3)
    down[3:] = up[:-3] + 0.6 * rng.standard_normal(1497)   # up leads down by 3
    # IGV drawn last so the up/down RNG sequence above is unchanged. The cloud
    # node maps to IGV (chips -> SOXX, cloud -> IGV), mirroring production.
    igv = 0.7 * spy + 0.5 * rng.standard_normal(1500)
    frames = []
    for tkr, vals in {"SPY": spy, "SOXX": soxx, "IGV": igv, "UP": up, "DOWN": down}.items():
        frames.append(pd.DataFrame({"ticker": tkr, "date": idx, "log_return": vals}))
    return pd.concat(frames, ignore_index=True)


def _nodes_edges():
    nodes = pd.DataFrame([
        {"id": "up", "tickers": json.dumps(["UP"]), "stage": "chips"},
        {"id": "down", "tickers": json.dumps(["DOWN"]), "stage": "cloud"},
    ])
    edges = pd.DataFrame([{"from_id": "up", "to_id": "down"}])
    return nodes, edges


def test_emits_one_row_per_edge_per_spec():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    specs = {r["factor_model"] for r in rows}
    assert specs == {"M1_market", "M2_market_sector"}
    assert len(rows) == 2  # 1 edge x 2 specs


def test_real_lead_lag_confirmed_and_correct_direction():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    for r in rows:
        assert r["lag"] >= 1
        assert r["m"] == 1
        assert r["contradicts_thesis"] is False


def test_bh_fdr_monotone():
    q = bh_fdr(np.array([0.001, 0.02, 0.5]))
    assert (np.diff(q) >= -1e-9).all()
    assert (q <= 1).all()
