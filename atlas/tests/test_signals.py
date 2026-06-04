import pandas as pd

from analysis.signals import h0_record
from analysis.signals import h1_record


def _edges_frame():
    # Two specs x two edges; M2 contemporaneous small, OOS sign 0.5, no FDR pass.
    rows = []
    for fm, contemp in [("M1_market", 0.14), ("M2_market_sector", 0.04)]:
        for left, right in [("a", "b"), ("c", "d")]:
            rows.append({
                "left": left, "right": right, "factor_model": fm,
                "corr_raw": 0.05, "corr_resid": 0.035, "corr_contemporaneous": contemp,
                "lag": 3, "q_value": 0.30, "oos_sign_rate": 0.5, "contradicts_thesis": False,
            })
    return pd.DataFrame(rows)


def test_h0_record_is_null_verdict_with_evidence_chain():
    rec = h0_record(_edges_frame())
    assert rec["id"] == "H0"
    assert rec["verdict"] == "null"
    # evidence chain ordered raw -> de-beta'd -> OOS
    stages = [e["stage"] for e in rec["evidence_chain"]]
    assert stages == ["raw contemporaneous", "sector de-beta'd", "OOS sign-retention"]
    assert rec["evidence_chain"][0]["value"] > rec["evidence_chain"][1]["value"]
    assert rec["stat"]["value"] == 0           # edges confirmed
    assert rec["stat"]["n"] == 2               # M2 edge count
    assert len(rec["detail_rows"]) == 2


def test_h0_confirmed_when_some_edge_passes():
    df = _edges_frame()
    df.loc[(df.factor_model == "M2_market_sector") & (df.left == "a"), "q_value"] = 0.01
    df.loc[(df.factor_model == "M2_market_sector") & (df.left == "a"), "oos_sign_rate"] = 0.8
    rec = h0_record(df)
    assert rec["stat"]["value"] == 1
    assert rec["verdict"] != "null"


def _h1_rows():
    # one strong edge (suggestive), one contradicting
    return pd.DataFrame([
        {"left": "applied_materials", "right": "tsmc", "lag": 2, "corr": 0.4,
         "slope": 0.6, "slope_lo": 0.2, "slope_hi": 1.0, "p_selection": 0.03,
         "q_value": 0.06, "contradicts_thesis": False, "n_quarters": 34},
        {"left": "nvidia", "right": "microsoft", "lag": 1, "corr": -0.1,
         "slope": -0.2, "slope_lo": -0.5, "slope_hi": 0.1, "p_selection": 0.6,
         "q_value": 0.6, "contradicts_thesis": True, "n_quarters": 30},
    ])


def test_h1_record_verdict_and_chain():
    rec = h1_record(_h1_rows())
    assert rec["id"] == "H1"
    assert rec["verdict"] in {"confirmed", "suggestive", "null", "contradicts"}
    assert rec["stat"]["n"] == 2
    assert rec["chart"]["type"] == "capex_revenue_overlay"
    assert len(rec["detail_rows"]) == 2
