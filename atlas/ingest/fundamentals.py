from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

import config
from config import CONCEPT_TAGS, DATA_RAW, SEC_RATE_LIMIT_SECONDS, SEC_USER_AGENT
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import FUNDAMENTAL_SCHEMA

CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
_CIK_RE = re.compile(r"\d{10}")
_TAG_RE = re.compile(r"[A-Za-z0-9]+")


def _validate_cik(cik: str) -> str:
    """SEC CIK must be exactly 10 digits before it enters the request URL."""
    if not _CIK_RE.fullmatch(cik):
        raise ValueError(f"invalid CIK (expected 10 digits): {cik!r}")
    return cik


def _validate_tag(tag: str) -> str:
    """us-gaap concept tags are alphanumeric; reject anything that could alter the URL path."""
    if not _TAG_RE.fullmatch(tag):
        raise ValueError(f"invalid us-gaap tag: {tag!r}")
    return tag


def _strict_mode() -> bool:
    """When ATLAS_INGEST_STRICT is set, a total ingest failure raises instead of writing
    an empty fallback (so CI fails fast rather than silently producing null verdicts)."""
    return bool(os.getenv("ATLAS_INGEST_STRICT"))
COLUMNS = [
    "cik",
    "ticker",
    "concept",
    "metric",
    "period_start",
    "period_end",
    "filed",
    "fiscal_period",
    "fy",
    "form",
    "value",
    "unit",
    "accn",
]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cik": pd.Series([], dtype="object"),
            "ticker": pd.Series([], dtype="object"),
            "concept": pd.Series([], dtype="object"),
            "metric": pd.Series([], dtype="object"),
            "period_start": pd.Series([], dtype="datetime64[ns]"),
            "period_end": pd.Series([], dtype="datetime64[ns]"),
            "filed": pd.Series([], dtype="datetime64[ns]"),
            "fiscal_period": pd.Series([], dtype="object"),
            "fy": pd.Series([], dtype="int64"),
            "form": pd.Series([], dtype="object"),
            "value": pd.Series([], dtype="float64"),
            "unit": pd.Series([], dtype="object"),
            "accn": pd.Series([], dtype="object"),
        }
    )


def normalize_concept(
    concept_json: dict, *, cik: str, ticker: str, metric: str, concept: str
) -> pd.DataFrame:
    """Flatten companyconcept JSON into validated long format."""
    obs = (concept_json.get("units", {}) or {}).get("USD", [])
    rows = [
        {
            "cik": cik,
            "ticker": ticker,
            "concept": concept,
            "metric": metric,
            "period_start": item.get("start"),
            "period_end": item.get("end"),
            "filed": item.get("filed"),
            "fiscal_period": item.get("fp"),
            "fy": item.get("fy"),
            "form": item.get("form"),
            "value": item.get("val"),
            "unit": "USD",
            "accn": item.get("accn"),
        }
        for item in obs
    ]
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return FUNDAMENTAL_SCHEMA.validate(_empty_frame())
    for col in ("period_start", "period_end", "filed"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["period_end", "filed", "value", "accn"]).reset_index(drop=True)
    if df.empty:
        return FUNDAMENTAL_SCHEMA.validate(_empty_frame())
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").fillna(0).astype("int64")
    return FUNDAMENTAL_SCHEMA.validate(df[COLUMNS])


def pick_first_filed(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the earliest-filed fact per metric and period_end."""
    if df.empty:
        return df
    return (
        df.sort_values("filed")
        .drop_duplicates(subset=["metric", "period_end"], keep="first")
        .reset_index(drop=True)
    )


def stitch_concepts(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine per-tag frames (given in priority order) into one continuous series.

    SEC filers drift their XBRL tag over time (e.g. NVDA capex moves from
    PaymentsToAcquirePropertyPlantAndEquipment to PaymentsToAcquireProductiveAssets),
    so a single tag truncates. We union all configured tags and, per period_end,
    keep the highest-priority tag that reports it (earliest-filed within that tag),
    filling coverage gaps with lower-priority fallbacks.
    """
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return _empty_frame()
    ranked = [f.assign(_prio=prio) for prio, f in enumerate(frames)]
    allf = pd.concat(ranked, ignore_index=True)
    allf = (
        allf.sort_values(["_prio", "filed"])
        .drop_duplicates(subset=["metric", "period_end"], keep="first")
        .drop(columns="_prio")
        .reset_index(drop=True)
    )
    return FUNDAMENTAL_SCHEMA.validate(allf[COLUMNS])


def fetch_concept(cik: str, tag: str) -> dict | None:  # pragma: no cover
    """Fetch one us-gaap company concept; return None when a filer lacks the tag."""

    url = CONCEPT_URL.format(cik=_validate_cik(cik), tag=_validate_tag(tag))

    def _download() -> dict | None:
        time.sleep(SEC_RATE_LIMIT_SECONDS)
        resp = requests.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    return with_retry(_download)


def resolve_metric(cik: str, ticker: str, metric: str) -> pd.DataFrame:  # pragma: no cover
    """Try configured fallback tags and return first-filed rows for a metric."""
    return _resolve_from_tags(cik, ticker, metric, metric)


def _resolve_from_tags(
    cik: str, ticker: str, tag_key: str, output_metric: str
) -> pd.DataFrame:  # pragma: no cover
    """Collect EVERY configured tag and stitch them so tag drift over time does
    not truncate coverage (see stitch_concepts)."""
    frames: list[pd.DataFrame] = []
    for tag in CONCEPT_TAGS[tag_key]:
        try:
            data = fetch_concept(cik, tag)
        except Exception as exc:  # noqa: BLE001 - one SEC failure must not abort ingest
            print(f"fundamentals: SKIP {ticker}:{tag} ({type(exc).__name__}: {exc})")
            continue
        if not data or not (data.get("units", {}) or {}).get("USD"):
            continue
        df = normalize_concept(data, cik=cik, ticker=ticker, metric=output_metric, concept=tag)
        if not df.empty:
            frames.append(pick_first_filed(df))
    return stitch_concepts(frames)


def _gross_margin(cik: str, ticker: str) -> pd.DataFrame:  # pragma: no cover
    rev = resolve_metric(cik, ticker, "revenue")
    gp = _resolve_from_tags(cik, ticker, "gross_profit", "revenue")
    if not rev.empty and not gp.empty:
        return _derive_gross_margin(rev, gp, lambda merged: merged["value_gp"] / merged["value"])

    cor = _resolve_from_tags(cik, ticker, "cost_of_revenue", "revenue")
    if rev.empty or cor.empty:
        return _empty_frame()
    return _derive_gross_margin(
        rev, cor, lambda merged: (merged["value"] - merged["value_cor"]) / merged["value"]
    )


def _derive_gross_margin(revenue: pd.DataFrame, other: pd.DataFrame, formula) -> pd.DataFrame:
    suffix = "_gp" if other["concept"].str.contains("GrossProfit").any() else "_cor"
    merged = revenue.merge(other[["period_end", "value"]], on="period_end", suffixes=("", suffix))
    if merged.empty:
        return _empty_frame()
    out = revenue.merge(
        merged.assign(gross_margin=formula(merged))[["period_end", "gross_margin"]],
        on="period_end",
        how="inner",
    )
    out = out.assign(metric="gross_margin", concept="derived", value=out["gross_margin"])
    return FUNDAMENTAL_SCHEMA.validate(out[COLUMNS].reset_index(drop=True))


def _ticker_from_node(raw_tickers: str) -> str:
    tickers = json.loads(raw_tickers)
    return tickers[0] if tickers else ""


def _load_nodes() -> pd.DataFrame:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        return con.execute(
            "select id, tickers, cik from graph_nodes where cik is not null and cik != ''"
        ).fetchdf()
    finally:
        con.close()


def run() -> None:  # pragma: no cover
    out_dir = Path(DATA_RAW) / "fundamentals"
    wrote_any = False
    unresolved: list[str] = []

    for _, node in _load_nodes().iterrows():
        ticker = _ticker_from_node(node["tickers"])
        cik = str(node["cik"]).zfill(10)
        frames = _frames_for_node(cik, ticker, unresolved)
        if frames:
            combined = FUNDAMENTAL_SCHEMA.validate(pd.concat(frames, ignore_index=True))
            atomic_write_parquet(combined, out_dir / f"{ticker}.parquet")
            wrote_any = True
            print(f"fundamentals: wrote {len(combined)} rows for {ticker}")

    if not wrote_any:
        if _strict_mode():
            raise RuntimeError(
                "fundamentals: all metrics failed and ATLAS_INGEST_STRICT is set "
                f"({len(unresolved)} unresolved)"
            )
        atomic_write_parquet(_empty_frame(), out_dir / "_empty.parquet")
        print("fundamentals: all metrics failed; wrote empty fallback parquet")
    if unresolved:
        print("fundamentals: unresolved (recorded, skipped):", ", ".join(unresolved))


def _frames_for_node(cik: str, ticker: str, unresolved: list[str]) -> list[pd.DataFrame]:
    frames = []
    for metric in ("revenue", "capex"):
        try:
            df = resolve_metric(cik, ticker, metric)
        except Exception as exc:  # noqa: BLE001 - tolerate failed CIK/metric fetch
            print(f"fundamentals: SKIP {ticker}:{metric} ({type(exc).__name__}: {exc})")
            unresolved.append(f"{ticker}:{metric}")
            continue
        if df.empty:
            unresolved.append(f"{ticker}:{metric}")
        else:
            frames.append(df)

    gm = _safe_gross_margin(cik, ticker, unresolved)
    return frames if gm.empty else [*frames, gm]


def _safe_gross_margin(cik: str, ticker: str, unresolved: list[str]) -> pd.DataFrame:
    try:
        gm = _gross_margin(cik, ticker)
    except Exception as exc:  # noqa: BLE001 - tolerate failed derived metric fetches
        print(f"fundamentals: SKIP {ticker}:gross_margin ({type(exc).__name__}: {exc})")
        unresolved.append(f"{ticker}:gross_margin")
        return _empty_frame()
    if gm.empty:
        unresolved.append(f"{ticker}:gross_margin")
    return gm


if __name__ == "__main__":  # pragma: no cover
    run()
