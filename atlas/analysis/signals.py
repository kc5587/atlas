"""Adapter: turn analysis tables into Signal Lab records (evidence chain + verdict).

Record builders are PURE (DataFrame in, dict out). build_signal_records wraps the
DuckDB reads. Verdict vocabulary: confirmed | suggestive | null | contradicts.
"""
from __future__ import annotations

import pandas as pd

FDR_ALPHA = 0.10
OOS_SIGN_FLOOR = 0.6


def h0_record(leadlag_edges: pd.DataFrame) -> dict:
    m1 = leadlag_edges[leadlag_edges["factor_model"] == "M1_market"]
    m2 = leadlag_edges[leadlag_edges["factor_model"] == "M2_market_sector"]
    raw_contemp = float(m1["corr_contemporaneous"].abs().median())
    resid_contemp = float(m2["corr_contemporaneous"].abs().median())
    oos = float(m2["oos_sign_rate"].median())
    confirmed = int(((m2["q_value"] <= FDR_ALPHA) & (m2["oos_sign_rate"] >= OOS_SIGN_FLOOR)
                     & (~m2["contradicts_thesis"])).sum())
    min_q = float(m2["q_value"].min()) if len(m2) else float("nan")
    verdict = "null" if confirmed == 0 else "suggestive"
    detail = m2[["left", "right", "corr_raw", "corr_resid", "lag", "q_value",
                 "oos_sign_rate"]].to_dict("records")
    return {
        "id": "H0", "title": "Daily lead/lag is sector beta", "horizon": "daily",
        "claim": "Upstream daily returns lead downstream daily returns",
        "mechanism": "If real, fast diffusion — but daily liquid names arbitrage it away",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw contemporaneous", "metric": "|corr|", "value": round(raw_contemp, 3)},
            {"stage": "sector de-beta'd", "metric": "|corr|", "value": round(resid_contemp, 3)},
            {"stage": "OOS sign-retention", "metric": "rate", "value": round(oos, 3)},
        ],
        "stat": {"name": "edges_confirmed", "value": confirmed,
                 "q_value": round(min_q, 3), "n": int(len(m2))},
        "caveats": ["Daily price→price only; co-moves but does not lead beyond sector beta"],
        "chart": {"type": "edge_corr_bars", "ref": "h0"},
        "detail_rows": detail,
    }


def build_signal_records(con) -> list[dict]:  # pragma: no cover (thin DB wrapper)
    edges = con.execute(
        'SELECT "left","right",factor_model,corr_raw,corr_resid,corr_contemporaneous,'
        'lag,q_value,oos_sign_rate,contradicts_thesis FROM leadlag WHERE pair_type=\'edge\''
    ).df()
    records = [h0_record(edges)]
    return records
