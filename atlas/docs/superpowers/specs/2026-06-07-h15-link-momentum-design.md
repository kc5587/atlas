# H15 — Link-Momentum (Cohen–Frazzini) Design Spec

**Date:** 2026-06-07
**Status:** Approved (design), pending implementation plan
**Scope:** One new Signal Lab card (H15) testing customer→supplier monthly return predictability along the value-chain graph, gating a long-short backtest. Additive — no existing H0–H12 verdict touched. This is the second of the two planned signal specs (after H11/H12).

---

## 1. Goal & rationale

Every existing equity-pricing test on the chain came back **null** (H2/H4/H5/H12) — the market prices the chain efficiently. H15 is the one hypothesis with a **documented friction** that those nulls do not rule out: **Cohen & Frazzini (2008), "Economic Links and Predictable Returns"** — investor limited attention causes a supplier's stock to under-react to news about its major **customers**, producing a predictable, tradeable return. The Atlas graph *is* a customer-supplier network, so the anomaly maps directly onto it.

**Why H0's null does not kill it:** H0 tested *daily contemporaneous* lead/lag and found sector beta. H15 tests *monthly, lagged, cross-sectional* predictability of **de-beta'd** returns — slow idiosyncratic-news diffusion, a different measurement. The de-beta is what proves the signal is not the H0 sector beta.

**Outcome discipline:** report the verdict exactly as produced. A null here is a strong, publishable result ("the canonical link anomaly is arbitraged away in mega-cap AI"); a confirm is the project's first genuine alpha candidate. The backtest is shown only if the test survives.

---

## 2. Hypothesis (pre-registered)

**Direction: customer→supplier only.** For a supplier node `S` with customer set `C(S) = {to_id : edge S→to}`, the equal-weight prior-month return of `C(S)` predicts `S`'s forward-month return.

- **Universe:** chain nodes with a daily price series → resampled to **monthly** log returns. A node is a testable supplier iff it has ≥1 customer that itself has returns, and ≥ `H15_MIN_MONTHS` (e.g. 36) months of history. Short-history names (ALAB, GEV, etc.) are excluded with a caveat. Uses the **full** graph (all stages) — H15 is returns-based, so the fundamentals-partition concern (see [[atlas-fundamentals-partition-gotcha]]) does not apply.
- **Single declared hypothesis** → tightest FDR, minimal multiple-testing burden.

---

## 3. Method — predictability test (rigorous core)

**De-beta (M2, the crux).** Compute each node's **M2-residual monthly return** = residual of the node's monthly return regressed on the monthly market (SPY) and its **orthogonalized sector** ETF (per `STAGE_SECTOR` → `FACTOR_TICKERS`), reusing `analysis/residualize.py` (`ols_residual` / `leave_one_out_sector` / `orthogonalize`) on monthly data. Betas are fit **in-sample only** (train index) to avoid look-ahead.

- **Signal** for supplier `S`, month `t`: `signal[S,t] = mean( resid_ret[c, t] for c in C(S) )` — customers' *idiosyncratic* month-`t` return. (Residual predictor: a positive slope means idiosyncratic news diffuses down-chain, not shared beta.)
- **Target:** `resid_ret[S, t+1]` (supplier's next-month residual return).
- **Estimation:** pooled-panel OLS slope `β` of target on signal across all `(S, t)`; block-bootstrap CI for `β` (reuse `bootstrap_slope_ci`); **selection-aware permutation p** via circular/block resample of the signal series (`significance.py`).
- **FDR:** BH over the declared family (single hypothesis; q reported for consistency).
- **OOS:** anchored walk-forward (`oos.py::walk_forward_folds`) — in each fold fit `β` on train, record the sign of the train→test relationship; report **OOS sign-rate** vs `OOS_SIGN_RATE_FLOOR` (0.6, descriptive heuristic, not a significance test).
- **Verdict:** `confirmed` if `β>0` & `q ≤ FDR_ALPHA` & OOS sign-rate ≥ floor; `suggestive` if `β>0` & CI lower bound > 0 but not FDR-significant; `contradicts` if a **statistically significant** `β<0`; else `null`.

---

## 4. Method — long-short backtest (gated)

Computed and shown **only if §3 verdict ∈ {confirmed, suggestive}**; otherwise the card is an honest null with no backtest block.

- Each month `t`: across testable suppliers, **long** those with `signal[S,t] > 0`, **short** those with `signal[S,t] < 0`, equal-weight each leg, **gross**. Portfolio return for month `t+1` uses **raw** monthly returns (what the strategy would actually earn).
- Restrict realized returns to the **walk-forward OOS** months (no in-sample P&L).
- **Metrics:** cumulative gross return, annualized return & vol, **Sharpe**, **alpha vs M2 + Newey–West t-stat** (regress monthly portfolio return on market + sector), **max drawdown**, `n_months`.
- **Explicit caveats:** gross of transaction costs / turnover / borrow; small universe (~20 names); equal-weight; 1-month horizon; no capacity analysis.

---

## 5. Code structure

| File | Responsibility | Action |
|---|---|---|
| `analysis/link_momentum.py` | monthly residual returns → signal panel → `link_predictability` → gated `link_backtest` | **Create** |
| `analysis/leadlag.py` | `run()` — compute + persist `link_momentum` table | Modify |
| `analysis/signals.py` | `h15_record` + wire into `build_signal_records` | Modify |
| `config.py` | `H15_MIN_MONTHS`, horizon constant | Modify |
| `web/src/components/SignalCard.svelte` | new `link_momentum` chart block | Modify |
| `web/src/lib/signals.ts` | extend `detail_rows`/chart typing if needed | Modify |
| `tests/test_link_momentum.py` | unit tests | **Create** |
| `tests/test_signals.py` | `h15_record` verdict tests | Modify |

- **Functions (pure, testable):** `monthly_returns(returns)`, `residual_monthly_returns(monthly, factors, nodes)`, `link_signal_panel(resid, nodes, edges) -> DataFrame[node, month, signal, fwd_target]`, `link_predictability(panel, *, iters, seed) -> dict`, `link_backtest(panel, raw_monthly, factors) -> dict` (only invoked when gated).
- **Persistence:** `run()` builds one row table `CREATE OR REPLACE TABLE link_momentum` carrying both the predictability stats and (when gated) the backtest stats; `build_signal_records` reads it (guarded by `_has_table`) and appends `h15_record`.
- **Frontend:** a new `link_momentum` chart type in `SignalCard.svelte` that renders the predictability stat (slope, CI, q, OOS sign-rate) **and**, when present, the backtest summary (Sharpe, ann return, alpha, t-stat, max DD, n_months) as a stat table. **No equity-curve SVG** in v1 (stretch goal, out of scope).

---

## 6. Testing

- **Unit:** `link_signal_panel` builds the correct `(node, month, signal, fwd_target)` rows from a small synthetic graph; `link_predictability` returns a positive FDR-significant slope on a constructed "news diffuses" fixture and `null` on a noise fixture; `link_backtest` metrics (Sharpe, max DD) on a known return series; `h15_record` verdict mapping (confirmed/suggestive/null/contradicts).
- **Gating:** when the predictability fixture is null, `h15_record` contains no backtest block; when confirmed/suggestive, it does.
- **Pipeline:** regen `analysis.leadlag` → export; assert **H0–H12 records unchanged** (H15 is purely additive — same byte-level discipline, achievable here because H15 adds a table and reads only returns/edges).
- **Frontend:** web tests pass; H15 card validates against the signals schema with the new chart type.
- Report the verdict (and Sharpe/alpha if gated) exactly as produced.

---

## 7. Non-goals (explicit)

- No transaction-cost / turnover / borrow modeling (gross only, caveated).
- No leverage, no capacity/liquidity analysis.
- No factor model beyond M2 (market + orthogonalized sector).
- Single 1-month horizon; customer→supplier direction only.
- No equity-curve SVG chart in v1 (stat table only).
- No changes to any existing H0–H12 verdict or number.

---

## 8. Open items for the implementation plan

- Confirm the exact `residualize.py` API for monthly de-beta (function signatures, train-index handling) and the monthly resampling convention (sum of daily log returns per calendar month).
- Confirm `oos.py::walk_forward_folds` parameters appropriate for ~120 monthly observations (test/step/init_train_frac/embargo in *months*, not days).
- Confirm Newey–West lag for the alpha t-stat (e.g. 3) and the annualization convention (×12 / ×√12).
- Confirm `H15_MIN_MONTHS` (default 36) and the testable-supplier count after the filter.
- Decide the precise long-short construction at the margin (sign-based vs top/bottom tercile) — default **sign-based** for the small universe.
