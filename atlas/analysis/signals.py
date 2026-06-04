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


def h1_record(rows: pd.DataFrame) -> dict:
    n = int(len(rows))
    # Eligible = enough quarters AND a finite slope (short/degenerate edges excluded).
    elig = rows[(rows["n_quarters"] > 0) & rows["slope"].notna()]
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (elig["slope_lo"] > 0) & (~elig["contradicts_thesis"])]
    suggestive = elig[(elig["slope"] > 0) & (elig["slope_lo"] > 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif elig["contradicts_thesis"].any():
        verdict, best = "contradicts", elig.iloc[0]
    else:
        verdict = "null"
        best = elig.iloc[0] if len(elig) else rows.iloc[0]
    return {
        "id": "H1", "title": "Capex → downstream revenue", "horizon": "quarterly",
        "claim": "Upstream capex leads downstream revenue by 1–4 quarters",
        "mechanism": "Real lead times; markets update on quarterly guidance",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw |corr|", "metric": "|corr|", "value": round(float(elig["corr"].abs().median()), 3) if len(elig) else 0.0},
            {"stage": "best edge corr", "metric": "corr", "value": round(float(best["corr"]), 3)},
            {"stage": "best edge slope", "metric": "slope", "value": round(float(best["slope"]), 3)},
        ],
        "stat": {"name": "slope", "value": round(float(best["slope"]), 3),
                 "ci": [round(float(best["slope_lo"]), 3), round(float(best["slope_hi"]), 3)],
                 "q_value": round(float(best["q_value"]), 3), "n": n},
        "caveats": [f"~{int(elig['n_quarters'].median()) if len(elig) else 0} quarters/edge → CIs, no walk-forward",
                    "ASML/TSM excluded (no SEC fundamentals)"],
        "chart": {"type": "capex_revenue_overlay", "ref": "h1"},
        "detail_rows": elig[["left", "right", "lag", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_quarters"]].to_dict("records"),
    }


def build_signal_records(con) -> list[dict]:  # pragma: no cover
    edges = con.execute(
        'SELECT "left","right",factor_model,corr_raw,corr_resid,corr_contemporaneous,'
        'lag,q_value,oos_sign_rate,contradicts_thesis FROM leadlag WHERE pair_type=\'edge\''
    ).df()
    records = [h0_record(edges)]
    has_h1 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='fundamentals_leadlag'").fetchone()[0] > 0
    if has_h1:
        h1 = con.execute('SELECT * FROM fundamentals_leadlag').df()
        if len(h1):
            records.append(h1_record(h1))
    return records
