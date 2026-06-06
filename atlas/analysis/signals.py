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


def _num(x, ndigits: int = 3) -> float:
    """Round to a JSON-safe float; NaN/None -> 0.0 (card fields are required numbers)."""
    return 0.0 if x is None or pd.isna(x) else round(float(x), ndigits)


def h1_record(rows: pd.DataFrame) -> dict:
    # Eligible = enough quarters AND a finite slope (short/degenerate edges excluded).
    elig = rows[(rows["n_quarters"] > 0) & rows["slope"].notna()]
    n = int(len(elig))
    # Confirmation gate = the SELECTION-AWARE q (which already accounts for the
    # 1–4Q lag search) + expected sign + not contradicting. The slope CI is
    # conditional on the selected lag, so it does NOT gate "confirmed" — it only
    # qualifies the weaker "suggestive" tier and serves as a descriptive effect size.
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (~elig["contradicts_thesis"])]
    suggestive = elig[(elig["slope"] > 0) & (elig["slope_lo"] > 0)
                      & (~elig["contradicts_thesis"])]
    contradicting = elig[elig["contradicts_thesis"]]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.iloc[0]
    elif len(elig):
        verdict, best = "null", elig.iloc[0]
    else:
        verdict = "null"
        best = rows.iloc[0] if len(rows) else pd.Series(dtype=float)
    return {
        "id": "H1", "title": "Capex → downstream revenue", "horizon": "quarterly",
        "claim": "Upstream capex leads downstream revenue by 1–4 quarters",
        "mechanism": "Real lead times; markets update on quarterly guidance",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw |corr|", "metric": "|corr|",
             "value": _num(elig["corr"].abs().median()) if len(elig) else 0.0},
            {"stage": "best edge corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best edge slope", "metric": "slope", "value": _num(best.get("slope"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [f"~{int(elig['n_quarters'].median()) if len(elig) else 0} quarters/edge → CIs, no walk-forward",
                    "Slope CI is conditional on the selected lag; confirmation uses the selection-aware q",
                    "ASML/TSM excluded (no SEC fundamentals)"],
        "chart": {"type": "capex_revenue_overlay", "ref": "h1"},
        "detail_rows": elig[["left", "right", "lag", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_quarters"]].to_dict("records"),
    }


def h2_record(rows: pd.DataFrame) -> dict:
    elig = rows[rows["slope"].notna()]
    n = int(elig["n_events"].iloc[0]) if len(elig) else 0
    if not len(elig):
        verdict, best = "null", pd.Series(dtype=float)
    else:
        best = elig.iloc[0]
        q = float(best["q_value"])
        slope = float(best["slope"])
        lo = float(best["slope_lo"])
        if q <= FDR_ALPHA and slope > 0:
            verdict = "confirmed"
        elif q <= FDR_ALPHA and slope < 0:
            verdict = "contradicts"
        elif q <= 0.25 and slope > 0 and lo > 0:
            verdict = "suggestive"
        else:
            verdict = "null"
    interp = {
        "confirmed": "under-reaction (drift exists)",
        "suggestive": "weak drift",
        "null": "no drift (efficient)",
        "contradicts": "over-reaction / reversal",
    }[verdict]
    return {
        "id": "H2", "title": "Does a capex surprise drift into downstream returns?",
        "horizon": "weeks (event study)",
        "claim": "An upstream capex surprise predicts downstream forward drift",
        "mechanism": f"Post-announcement under-reaction -- verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "drift | positive surprise", "metric": "ret",
             "value": _num(best.get("pos_drift"))},
            {"stage": "drift | negative surprise", "metric": "ret",
             "value": _num(best.get("neg_drift"))},
            {"stage": "pooled slope", "metric": "slope", "value": _num(best.get("slope"))},
        ],
        "stat": {"name": "pooled_slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            f"horizon {int(best.get('horizon')) if len(elig) else 0}d; event-clustered (quarter-block bootstrap)",
            "effective n << event count; observational; no costs",
        ],
        "chart": {"type": "event_drift", "ref": "h2"},
        "detail_rows": elig[["horizon", "slope", "slope_lo", "slope_hi", "q_value",
                             "n_events", "pos_drift", "neg_drift"]].to_dict("records"),
    }


def h6_record(rows: pd.DataFrame) -> dict:
    """H6: variance risk premium + implied-vol information content."""
    elig = rows[rows["mean_vrp"].notna()]
    if not len(elig):
        verdict, best, n = "null", pd.Series(dtype=float), 0
    else:
        best = elig.sort_values("mean_vrp", ascending=False).iloc[0]
        n = int(best["n_obs"])
        premium = best["mean_vrp"] > 0 and best["vrp_lo"] > 0
        info = best["incremental_oos_r2"] > 0
        neg_premium = best["mean_vrp"] < 0 and best["vrp_hi"] < 0
        if premium and info:
            verdict = "confirmed"
        elif premium or info:
            verdict = "suggestive"
        elif neg_premium:
            verdict = "contradicts"
        else:
            verdict = "null"
    interp = {
        "confirmed": "options price risk informatively (premium + forecast content)",
        "suggestive": "partial: premium or forecast content, not both",
        "null": "no measurable premium / no added forecast content",
        "contradicts": "implied below realized (negative premium)",
    }[verdict]
    return {
        "id": "H6",
        "title": "Implied vol carries information: the variance risk premium",
        "horizon": "1 month (21d realized)",
        "claim": "Implied variance exceeds subsequent realized variance, and IV forecasts RV",
        "mechanism": f"Options market charges a variance risk premium -- verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "mean variance risk premium", "metric": "var",
             "value": _num(best.get("mean_vrp"))},
            {"stage": "VRP 90% CI low", "metric": "var", "value": _num(best.get("vrp_lo"))},
            {"stage": "IV incremental OOS R2", "metric": "r2",
             "value": _num(best.get("incremental_oos_r2"))},
        ],
        "stat": {"name": "mean_vrp", "value": _num(best.get("mean_vrp")),
                 "ci": [_num(best.get("vrp_lo")), _num(best.get("vrp_hi"))],
                 "q_value": None, "n": n},
        "caveats": [
            "Index/sector level: VIX<->SPY, VXN<->QQQ. No free semis implied series exists.",
            "Overlapping 21d windows -> block-bootstrap CI; observational, no costs.",
        ],
        "chart": {"type": "vrp_term", "ref": "h6"},
        "detail_rows": elig[["pair", "mean_vrp", "vrp_lo", "vrp_hi",
                             "incremental_oos_r2", "n_obs"]].to_dict("records"),
    }


def h7_record(rows: pd.DataFrame) -> dict:
    """H7: vol term-structure slope as a forward-return timer."""
    elig = rows[(rows["n_obs"] > 0) & rows["slope"].notna()]
    confirmed = elig[
        (elig["q_value"] <= FDR_ALPHA)
        & (elig["slope"] > 0)
        & (~elig["contradicts_thesis"])
        & (elig["oos_sign_rate"] >= OOS_SIGN_FLOOR)
    ]
    suggestive = elig[
        (elig["q_value"] <= 0.25)
        & (elig["slope"] > 0)
        & (elig["slope_lo"] > 0)
        & (~elig["contradicts_thesis"])
    ]
    contradicting = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] < 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.sort_values("q_value").iloc[0]
    elif len(elig):
        verdict, best = "null", elig.sort_values("q_value").iloc[0]
    else:
        verdict, best = "null", (rows.iloc[0] if len(rows) else pd.Series(dtype=float))
    interp = {
        "confirmed": "a compensated volatility-risk premium, not a free edge",
        "suggestive": "weak, possibly a risk premium",
        "null": "no reliable timing signal",
        "contradicts": "term structure times returns the wrong way",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H7",
        "title": "Does the vol term-structure slope time forward sector returns?",
        "horizon": "1-3 months",
        "claim": "VIX/VIX3M backwardation predicts positive forward sector returns",
        "mechanism": f"VIX/VIX3M is a volatility-risk-premium proxy: backwardation pays "
                     f"for bearing stress, consistent with efficient markets -- {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best-cell corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best-cell slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "OOS sign-retention", "metric": "rate",
             "value": _num(best.get("oos_sign_rate"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            "Predictor is S&P term structure (VXN has no free term structure); targets raw forward returns.",
            "All 9 cells (3 targets x 3 horizons) are one correlated effect, not independent findings; BH-FDR over the family.",
            "A RISK premium, not alpha: it pays off by bearing volatility/crash risk. Observational; no costs or tail-risk modeled.",
        ],
        "chart": {"type": "termstructure_timing", "ref": "h7"},
        "detail_rows": elig[["target", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                             "q_value", "oos_sign_rate", "n_obs"]].to_dict("records"),
    }


def h5_record(rows: pd.DataFrame) -> dict:
    elig = rows[(rows["n_obs"] > 0) & rows["slope"].notna()]
    n = int(len(elig))
    confirmed = elig[
        (elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0) & (~elig["contradicts_thesis"])
    ]
    suggestive = elig[
        (elig["q_value"] <= 0.25)
        & (elig["slope"] > 0)
        & (elig["slope_lo"] > 0)
        & (~elig["contradicts_thesis"])
    ]
    # "Contradicts" must be a STATISTICALLY SIGNIFICANT reversal (negative slope
    # passing FDR) — not a near-zero negative slope. Otherwise it is just noise =>
    # priced in (null). A slope of -0.014 with q=1.0 is not a reversal claim.
    contradicting = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] < 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.sort_values("q_value").iloc[0]
    elif len(elig):
        # Null: surface the closest-to-significant edge so the card shows that even
        # the strongest link does not pass ("priced in"), not an arbitrary edge.
        verdict, best = "null", elig.sort_values("q_value").iloc[0]
    else:
        verdict = "null"
        best = rows.iloc[0] if len(rows) else pd.Series(dtype=float)
    interp = {
        "confirmed": "not yet priced in",
        "suggestive": "weak under-pricing signal",
        "null": "priced in",
        "contradicts": "over-reaction / reversal",
    }[verdict]
    return {
        "id": "H5", "title": "Is upstream capex priced into downstream equity?",
        "horizon": "1-2 quarters forward",
        "claim": "Upstream capex growth predicts downstream forward returns",
        "mechanism": f"Under-reaction to a slow real signal -- verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best edge corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best edge slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "selected horizon (days)", "metric": "days",
             "value": _num(best.get("horizon"), 0)},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            f"~{int(elig['n_obs'].median()) if len(elig) else 0} filings/edge; overlapping forward windows",
            "Confirmed means not-yet-priced-in; Null means priced in",
            "Observational, point-in-time on filing date; no costs/turnover",
        ],
        "chart": {"type": "capex_price", "ref": "h5"},
        "detail_rows": elig[["left", "right", "horizon", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_obs"]].to_dict("records"),
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
    has_h5 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='capex_price'").fetchone()[0] > 0
    if has_h5:
        h5 = con.execute('SELECT * FROM capex_price').df()
        if len(h5):
            records.append(h5_record(h5))
    has_h2 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='event_drift'").fetchone()[0] > 0
    if has_h2:
        h2 = con.execute('SELECT * FROM event_drift').df()
        if len(h2):
            records.append(h2_record(h2))
    has_h6 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='vol_premium'").fetchone()[0] > 0
    if has_h6:
        h6 = con.execute('SELECT * FROM vol_premium').df()
        if len(h6):
            records.append(h6_record(h6))
    has_h7 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='vol_termstructure'").fetchone()[0] > 0
    if has_h7:
        h7 = con.execute('SELECT * FROM vol_termstructure').df()
        if len(h7):
            records.append(h7_record(h7))
    return records
