import math

import pandas as pd

from analysis.signals import build_signal_records, h0_record, h1_record, h2_record, h5_record


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


def test_h0_record_empty_edges_emit_finite_numeric_fields():
    cols = [
        "left", "right", "factor_model", "corr_raw", "corr_resid",
        "corr_contemporaneous", "lag", "q_value", "oos_sign_rate",
        "contradicts_thesis",
    ]

    rec = h0_record(pd.DataFrame(columns=cols))

    assert all(math.isfinite(e["value"]) for e in rec["evidence_chain"])
    assert math.isfinite(rec["stat"]["value"])
    assert math.isfinite(rec["stat"]["q_value"])
    assert math.isfinite(rec["stat"]["n"])


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


def test_h1_record_suggestive_when_ci_positive_but_fdr_not_passed():
    rows = _h1_rows()
    rows.loc[0, "q_value"] = 0.24
    rec = h1_record(rows)
    assert rec["verdict"] == "suggestive"


def test_h1_confirmed_gates_on_selection_aware_q_not_the_ci():
    # Edge passes FDR with positive slope but a CI that touches 0; the
    # selection-conditional CI must NOT block 'confirmed' (review HIGH-2).
    rows = pd.DataFrame([
        {"left": "a", "right": "b", "lag": 2, "corr": 0.4, "slope": 0.5,
         "slope_lo": -0.1, "slope_hi": 1.1, "p_selection": 0.02, "q_value": 0.05,
         "contradicts_thesis": False, "n_quarters": 28},
    ])
    assert h1_record(rows)["verdict"] == "confirmed"


def test_h1_n_counts_eligible_only_and_emits_no_nan():
    import math
    import numpy as np
    rows = pd.DataFrame([
        {"left": "a", "right": "b", "lag": 2, "corr": 0.4, "slope": 0.5,
         "slope_lo": 0.2, "slope_hi": 0.8, "p_selection": 0.02, "q_value": 0.05,
         "contradicts_thesis": False, "n_quarters": 28},
        {"left": "x", "right": "b", "lag": 0, "corr": np.nan, "slope": np.nan,
         "slope_lo": np.nan, "slope_hi": np.nan, "p_selection": 1.0,
         "q_value": np.nan, "contradicts_thesis": False, "n_quarters": 2},
    ])
    rec = h1_record(rows)
    assert rec["stat"]["n"] == 1                      # degenerate edge excluded from n
    assert not math.isnan(rec["stat"]["value"])
    assert all(not math.isnan(s["value"]) for s in rec["evidence_chain"])


def test_h1_all_degenerate_is_null_without_nan():
    import math
    import numpy as np
    rows = pd.DataFrame([
        {"left": "a", "right": "b", "lag": 0, "corr": np.nan, "slope": np.nan,
         "slope_lo": np.nan, "slope_hi": np.nan, "p_selection": 1.0,
         "q_value": np.nan, "contradicts_thesis": False, "n_quarters": 1},
    ])
    rec = h1_record(rows)
    assert rec["verdict"] == "null" and rec["stat"]["n"] == 0
    assert not math.isnan(rec["stat"]["value"])


def test_build_signal_records_appends_h1_when_table_exists():
    class Result:
        def __init__(self, df=None, row=None):
            self._df = df
            self._row = row

        def df(self):
            return self._df

        def fetchone(self):
            return self._row

    class Con:
        def execute(self, sql):
            if "FROM leadlag" in sql:
                return Result(df=_edges_frame())
            if "table_name='capex_price'" in sql:
                return Result(row=(0,))
            if "table_name='networking_propagation'" in sql:
                return Result(row=(0,))
            if "table_name='networking_pricing'" in sql:
                return Result(row=(0,))
            if "table_name='event_drift'" in sql:
                return Result(row=(0,))
            if "table_name='vol_premium'" in sql:
                return Result(row=(0,))
            if "table_name='vol_termstructure'" in sql:
                return Result(row=(0,))
            if "table_name='leading_revenue'" in sql:
                return Result(row=(0,))
            if "table_name='power_margins'" in sql:
                return Result(row=(0,))
            if "table_name='power_demand'" in sql:
                return Result(row=(0,))
            if "table_name='macro_sector'" in sql:
                return Result(row=(0,))
            if "table_name='link_momentum'" in sql:
                return Result(row=(0,))
            if "information_schema.tables" in sql:
                return Result(row=(1,))
            if "fundamentals_leadlag" in sql:
                return Result(df=_h1_rows())
            raise AssertionError(sql)

    records = build_signal_records(Con())
    assert [r["id"] for r in records] == ["H0", "H1"]


def test_h15_record_confirmed_includes_backtest():
    from analysis.signals import h15_record

    row = pd.DataFrame([{
        "slope": 0.12,
        "slope_lo": 0.03,
        "slope_hi": 0.21,
        "p_value": 0.01,
        "q_value": 0.01,
        "oos_sign_rate": 0.72,
        "n_obs": 480,
        "n_nodes": 8,
        "n_months": 60,
        "n_folds": 4,
        "gated": True,
        "sharpe": 0.9,
        "ann_return": 0.11,
        "ann_vol": 0.12,
        "alpha": 0.08,
        "t_stat": 2.3,
        "max_drawdown": -0.18,
        "n_months_bt": 48,
    }])

    rec = h15_record(row)

    assert rec["id"] == "H15"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "link_momentum"
    assert any("sharpe" in str(row).lower() for row in rec["detail_rows"])


def test_h15_record_null_has_no_backtest_row():
    from analysis.signals import h15_record

    row = pd.DataFrame([{
        "slope": 0.01,
        "slope_lo": -0.05,
        "slope_hi": 0.07,
        "p_value": 0.6,
        "q_value": 0.6,
        "oos_sign_rate": 0.5,
        "n_obs": 400,
        "n_nodes": 8,
        "n_months": 55,
        "n_folds": 4,
        "gated": False,
    }])

    rec = h15_record(row)

    assert rec["verdict"] == "null"
    assert rec["detail_rows"] == []


def test_build_signal_records_appends_h15_when_table_exists():
    class Result:
        def __init__(self, df=None, row=None):
            self._df = df
            self._row = row

        def df(self):
            return self._df

        def fetchone(self):
            return self._row

    class Con:
        def execute(self, sql):
            if "FROM leadlag" in sql:
                return Result(df=_edges_frame())
            if "SELECT * FROM link_momentum" in sql:
                return Result(df=pd.DataFrame([{
                    "slope": 0.12,
                    "slope_lo": 0.03,
                    "slope_hi": 0.21,
                    "p_value": 0.01,
                    "q_value": 0.01,
                    "oos_sign_rate": 0.72,
                    "n_obs": 480,
                    "n_nodes": 8,
                    "n_months": 60,
                    "n_folds": 4,
                    "gated": False,
                }]))
            if "table_name='link_momentum'" in sql:
                return Result(row=(1,))
            if "information_schema.tables" in sql:
                return Result(row=(0,))
            raise AssertionError(sql)

    records = build_signal_records(Con())

    assert [record["id"] for record in records] == ["H0", "H15"]


def _h5_rows(slope=0.6, q=0.05, contra=False):
    return pd.DataFrame(
        [
            {
                "left": "broadcom",
                "right": "google",
                "horizon": 63,
                "corr": 0.5,
                "slope": slope,
                "slope_lo": 0.2,
                "slope_hi": 1.0,
                "p_selection": 0.02,
                "q_value": q,
                "contradicts_thesis": contra,
                "n_obs": 25,
            },
        ]
    )


def test_h5_confirmed_means_not_priced_in():
    rec = h5_record(_h5_rows(slope=0.6, q=0.05))
    assert rec["id"] == "H5"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "capex_price"


def test_h5_null_means_priced_in():
    rec = h5_record(_h5_rows(slope=0.05, q=0.8))
    assert rec["verdict"] == "null"


def test_h5_insignificant_negative_slope_is_null_not_contradicts():
    # slope slightly negative, CI straddles 0, q=1.0 -> no effect -> priced in (null),
    # NOT a 'contradicts'/reversal claim.
    rows = pd.DataFrame([
        {"left": "a", "right": "b", "horizon": 126, "corr": -0.1, "slope": -0.014,
         "slope_lo": -0.049, "slope_hi": 0.02, "p_selection": 0.9, "q_value": 1.0,
         "contradicts_thesis": True, "n_obs": 25},
    ])
    assert h5_record(rows)["verdict"] == "null"


def test_h5_significant_reversal_is_contradicts():
    # genuine reversal: negative slope, CI excludes 0, passes FDR
    rows = pd.DataFrame([
        {"left": "a", "right": "b", "horizon": 63, "corr": -0.5, "slope": -0.4,
         "slope_lo": -0.6, "slope_hi": -0.2, "p_selection": 0.01, "q_value": 0.05,
         "contradicts_thesis": True, "n_obs": 25},
    ])
    assert h5_record(rows)["verdict"] == "contradicts"


def test_h11_record_confirmed_on_positive_significant_edge():
    from analysis.signals import h11_record
    rows = pd.DataFrame([{
        "left": "microsoft", "right": "arista", "lag": 1, "corr": 0.7,
        "slope": 0.8, "slope_lo": 0.2, "slope_hi": 1.4, "p_selection": 0.001,
        "q_value": 0.01, "n_quarters": 16, "contradicts_thesis": False,
    }])
    rec = h11_record(rows)
    assert rec["id"] == "H11"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "capex_revenue_overlay"


def test_h12_record_null_when_not_priced():
    from analysis.signals import h12_record
    rows = pd.DataFrame([{
        "left": "microsoft", "right": "arista", "horizon": 63, "corr": 0.05,
        "slope": 0.01, "slope_lo": -0.3, "slope_hi": 0.32, "p_selection": 0.8,
        "q_value": 0.9, "n_obs": 18, "contradicts_thesis": False,
    }])
    rec = h12_record(rows)
    assert rec["id"] == "H12"
    assert rec["verdict"] == "null"
    assert rec["chart"]["type"] == "capex_price"


def _h2_row(slope=0.01, q=0.05, neg=False):
    return pd.DataFrame(
        [
            {
                "horizon": 42,
                "slope": slope,
                "slope_lo": 0.004,
                "slope_hi": 0.02,
                "p_selection": 0.02,
                "q_value": q,
                "n_events": 120,
                "pos_drift": 0.01,
                "neg_drift": -0.008,
                "contradicts_thesis": neg,
            }
        ]
    )


def test_h2_confirmed_when_significant_positive_drift():
    assert h2_record(_h2_row(slope=0.01, q=0.05))["verdict"] == "confirmed"


def test_h2_null_when_insignificant():
    assert h2_record(_h2_row(slope=0.001, q=0.8))["verdict"] == "null"


def test_h8_record_confirmed_and_null():
    from analysis.signals import h8_record

    confirmed = pd.DataFrame(
        [
            {
                "indicator": "IPG3344S",
                "best_lead": 1,
                "corr": 0.5,
                "slope": 0.8,
                "slope_lo": 0.3,
                "slope_hi": 1.2,
                "p_selection": 0.001,
                "q_value": 0.004,
                "n_obs": 45,
                "contradicts_thesis": False,
            },
            {
                "indicator": "A34SNO",
                "best_lead": 2,
                "corr": 0.2,
                "slope": 0.3,
                "slope_lo": -0.1,
                "slope_hi": 0.7,
                "p_selection": 0.2,
                "q_value": 0.2,
                "n_obs": 45,
                "contradicts_thesis": False,
            },
        ]
    )
    rec = h8_record(confirmed)
    assert rec["id"] == "H8" and rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "leading_revenue"

    nullish = pd.DataFrame(
        [
            {
                "indicator": "IPG3344S",
                "best_lead": 1,
                "corr": 0.05,
                "slope": 0.1,
                "slope_lo": -0.2,
                "slope_hi": 0.4,
                "p_selection": 0.4,
                "q_value": 0.6,
                "n_obs": 45,
                "contradicts_thesis": False,
            },
        ]
    )
    assert h8_record(nullish)["verdict"] == "null"


def test_h4_record_null_surfaces_min_q():
    from analysis.signals import h4_record

    rows = pd.DataFrame(
        [
            {
                "indicator": "IPG3344S",
                "horizon": 1,
                "corr": 0.05,
                "slope": 0.4,
                "slope_lo": -0.3,
                "slope_hi": 1.1,
                "p_selection": 0.3,
                "q_value": 0.5,
                "oos_sign_rate": 0.5,
                "n_obs": 150,
                "contradicts_thesis": False,
            },
            {
                "indicator": "A34SNO",
                "horizon": 3,
                "corr": 0.07,
                "slope": 0.6,
                "slope_lo": -0.1,
                "slope_hi": 1.3,
                "p_selection": 0.12,
                "q_value": 0.3,
                "oos_sign_rate": 0.55,
                "n_obs": 150,
                "contradicts_thesis": False,
            },
        ]
    )
    rec = h4_record(rows)
    assert rec["id"] == "H4" and rec["verdict"] == "null"
    assert rec["chart"]["type"] == "macro_sector"
    assert rec["stat"]["q_value"] == 0.3


def test_h4_record_confirmed():
    from analysis.signals import h4_record

    rows = pd.DataFrame(
        [
            {
                "indicator": "IPG3344S",
                "horizon": 3,
                "corr": 0.3,
                "slope": 0.9,
                "slope_lo": 0.4,
                "slope_hi": 1.4,
                "p_selection": 0.001,
                "q_value": 0.01,
                "oos_sign_rate": 0.8,
                "n_obs": 150,
                "contradicts_thesis": False,
            },
        ]
    )
    assert h4_record(rows)["verdict"] == "confirmed"


def test_h6_record_confirmed_when_premium_and_info():
    from analysis.signals import h6_record

    rows = pd.DataFrame([
        {"pair": "^VIX~SPY", "implied": "^VIX", "underlying": "SPY",
         "mean_vrp": 0.02, "vrp_lo": 0.012, "vrp_hi": 0.03,
         "incremental_oos_r2": 0.08, "n_obs": 2500},
        {"pair": "^VXN~QQQ", "implied": "^VXN", "underlying": "QQQ",
         "mean_vrp": 0.03, "vrp_lo": 0.02, "vrp_hi": 0.04,
         "incremental_oos_r2": 0.05, "n_obs": 2500},
    ])
    rec = h6_record(rows)
    assert rec["id"] == "H6"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "vrp_term"
    assert rec["stat"]["n"] == 2500
    assert len(rec["evidence_chain"]) >= 2


def test_h6_record_null_when_no_premium():
    from analysis.signals import h6_record

    rows = pd.DataFrame([
        {"pair": "^VIX~SPY", "implied": "^VIX", "underlying": "SPY",
         "mean_vrp": 0.001, "vrp_lo": -0.004, "vrp_hi": 0.006,
         "incremental_oos_r2": -0.01, "n_obs": 2500},
    ])
    assert h6_record(rows)["verdict"] == "null"


def test_h7_record_null_surfaces_min_q_cell():
    from analysis.signals import h7_record

    rows = pd.DataFrame([
        {"target": "SPY", "horizon": 21, "corr": 0.04, "slope": 0.5, "slope_lo": -0.2,
         "slope_hi": 1.2, "p_selection": 0.30, "q_value": 0.55, "oos_sign_rate": 0.5,
         "n_obs": 2000, "contradicts_thesis": False},
        {"target": "SOXX", "horizon": 63, "corr": 0.06, "slope": 0.8, "slope_lo": -0.1,
         "slope_hi": 1.6, "p_selection": 0.12, "q_value": 0.40, "oos_sign_rate": 0.55,
         "n_obs": 2000, "contradicts_thesis": False},
    ])
    rec = h7_record(rows)
    assert rec["id"] == "H7"
    assert rec["verdict"] == "null"
    assert rec["chart"]["type"] == "termstructure_timing"
    assert rec["stat"]["q_value"] == 0.40


def test_h7_record_confirmed_when_cell_passes():
    from analysis.signals import h7_record

    rows = pd.DataFrame([
        {"target": "SOXX", "horizon": 21, "corr": 0.12, "slope": 1.1, "slope_lo": 0.3,
         "slope_hi": 1.9, "p_selection": 0.01, "q_value": 0.05, "oos_sign_rate": 0.7,
         "n_obs": 2000, "contradicts_thesis": False},
    ])
    assert h7_record(rows)["verdict"] == "confirmed"


def test_h7_confirmed_framed_as_risk_premium_not_alpha():
    # Honesty guard: a confirmed H7 must be framed as a compensated risk premium,
    # never as 'free alpha / not priced in' (it is a volatility-risk-premium proxy).
    from analysis.signals import h7_record

    rows = pd.DataFrame([
        {"target": "SPY", "horizon": 63, "corr": 0.25, "slope": 0.21, "slope_lo": 0.16,
         "slope_hi": 0.27, "p_selection": 0.001, "q_value": 0.003, "oos_sign_rate": 1.0,
         "n_obs": 4099, "contradicts_thesis": False},
    ])
    rec = h7_record(rows)
    assert rec["verdict"] == "confirmed"
    mech = rec["mechanism"].lower()
    assert "risk" in mech and "premium" in mech
    assert "harvestable" not in mech and "not priced in" not in mech
    assert any("risk premium" in c.lower() for c in rec["caveats"])


def test_h8_caveat_names_driver_and_flags_korea_canary():
    from analysis.signals import h8_record
    rows = pd.DataFrame([
        {"indicator": "CAPUTLG3344S", "best_lead": 1, "corr": 0.45, "slope": 2.6,
         "slope_lo": 1.7, "slope_hi": 4.1, "p_selection": 0.009, "q_value": 0.045,
         "n_obs": 60, "contradicts_thesis": False},
        {"indicator": "XTEXVA01KRM664S", "best_lead": 1, "corr": 0.13, "slope": 0.6,
         "slope_lo": -0.24, "slope_hi": 1.9, "p_selection": 0.37, "q_value": 0.39,
         "n_obs": 60, "contradicts_thesis": False},
    ])
    rec = h8_record(rows)
    assert rec["verdict"] == "confirmed"
    joined = " ".join(rec["caveats"])
    assert "CAPUTLG3344S" in joined
    assert "Korea export 'canary'" in joined


def test_h9_record_confirmed_compression_and_null():
    from analysis.signals import h9_record

    conf = pd.DataFrame([
        {"indicator": "WPU0543", "best_lead": 1, "corr": 0.4, "slope": 0.02,
         "slope_lo": 0.005, "slope_hi": 0.04, "p_selection": 0.002, "q_value": 0.01,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    rec = h9_record(conf)
    assert rec["id"] == "H9" and rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "power_margins"

    nul = pd.DataFrame([
        {"indicator": "WPU0543", "best_lead": 0, "corr": 0.05, "slope": 0.001,
         "slope_lo": -0.01, "slope_hi": 0.02, "p_selection": 0.5, "q_value": 0.7,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    assert h9_record(nul)["verdict"] == "null"


def test_h10_record_null_and_confirmed():
    from analysis.signals import h10_record

    nul = pd.DataFrame([
        {"name": "VST", "horizon": 1, "corr": 0.05, "slope": 0.4, "slope_lo": -0.3,
         "slope_hi": 1.1, "p_selection": 0.3, "q_value": 0.5, "oos_sign_rate": 0.5,
         "n_obs": 120, "contradicts_thesis": False},
        {"name": "ETN", "horizon": 3, "corr": 0.07, "slope": 0.6, "slope_lo": -0.1,
         "slope_hi": 1.3, "p_selection": 0.12, "q_value": 0.3, "oos_sign_rate": 0.55,
         "n_obs": 150, "contradicts_thesis": False},
    ])
    rec = h10_record(nul)
    assert rec["id"] == "H10" and rec["verdict"] == "null"
    assert rec["chart"]["type"] == "power_demand"
    assert rec["stat"]["q_value"] == 0.3

    conf = pd.DataFrame([
        {"name": "CEG", "horizon": 3, "corr": 0.3, "slope": 1.0, "slope_lo": 0.4,
         "slope_hi": 1.6, "p_selection": 0.001, "q_value": 0.01, "oos_sign_rate": 0.8,
         "n_obs": 120, "contradicts_thesis": False},
    ])
    assert h10_record(conf)["verdict"] == "confirmed"
