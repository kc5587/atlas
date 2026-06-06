# atlas/web/export_data.py
from __future__ import annotations

import argparse
import math
import json
from numbers import Real
from pathlib import Path

import duckdb

SCHEMA_VERSION = "2"
REQUIRED = ["graph_nodes", "graph_edges", "leadlag"]
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "atlas.duckdb"
DEFAULT_OUT = Path(__file__).resolve().parent / "static" / "data"


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()[0] > 0


def downsample(points: list[dict], *, max_points: int) -> list[dict]:
    """Evenly thin a time series to <= max_points, always keeping first and last."""
    n = len(points)
    if max_points < 2 or n <= max_points:
        return points
    step = (n - 1) / (max_points - 1)
    idx = sorted({round(i * step) for i in range(max_points)} | {0, n - 1})
    return [points[i] for i in idx]


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, Real):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        if hasattr(value, "item"):
            return value.item()
    return value


def _write_json(path: Path, value, *, default=None) -> None:
    path.write_text(json.dumps(_json_safe(value), default=default, allow_nan=False))


def _criticality(node_id: str, edges: list[dict]) -> float:
    deg = sum(1 for e in edges if e["from_id"] == node_id or e["to_id"] == node_id)
    return float(deg)


def export_all(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    from config import FACTOR_TICKERS

    for t in REQUIRED:
        if not _has_table(con, t):
            raise RuntimeError(f"missing required table: {t}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    edges = con.execute(
        "SELECT from_id, to_id, relationship, note, evidence, as_of FROM graph_edges"
    ).df().to_dict("records")
    # cik only exists after Layer 2; select it conditionally so this works pre- and post-L2.
    has_cik = con.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='graph_nodes' AND column_name='cik'"
    ).fetchone()[0] > 0
    cik_sel = "COALESCE(cik, '') AS cik" if has_cik else "'' AS cik"
    raw_nodes = con.execute(
        f"SELECT id, name, tickers, stage, region, {cik_sel} FROM graph_nodes"
    ).df().to_dict("records")
    nodes = []
    for n in raw_nodes:
        nodes.append({
            "id": n["id"], "name": n["name"],
            "tickers": json.loads(n["tickers"]) if n["tickers"] else [],
            "stage": n["stage"], "region": n["region"],
            "cik": n["cik"] or None,
            "criticality": _criticality(n["id"], edges),
        })
    _write_json(out_dir / "graph.json", {"nodes": nodes, "edges": edges})

    leadlag = con.execute("SELECT * FROM leadlag").df().to_dict("records")
    _write_json(out_dir / "leadlag.json", leadlag, default=str)

    prices: dict[str, list[dict]] = {}
    if _has_table(con, "returns"):
        factor_set = set(FACTOR_TICKERS.values())
        df = con.execute(
            "SELECT ticker, date, sum(log_return) OVER (PARTITION BY ticker ORDER BY date) AS cum "
            "FROM returns ORDER BY ticker, date"
        ).df()
        for ticker, grp in df.groupby("ticker"):
            if ticker in factor_set:
                continue
            pts = [{"date": str(d.date()), "value": float(v)}
                   for d, v in zip(grp["date"], grp["cum"])]
            prices[ticker] = downsample(pts, max_points=400)
    series: dict = {"prices": prices}

    if _has_table(con, "fundamentals_quarterly"):
        fdf = con.execute(
            "SELECT ticker, period_end, revenue, capex, gross_margin "
            "FROM fundamentals_quarterly ORDER BY ticker, period_end"
        ).df()
        fund: dict = {}
        for ticker, grp in fdf.groupby("ticker"):
            def col(c):
                return [{"date": str(d.date()), "value": (None if v != v else float(v))}
                        for d, v in zip(grp["period_end"], grp[c])]
            fund[ticker] = {"revenue": col("revenue"), "capex": col("capex"),
                            "gross_margin": col("gross_margin")}
        series["fundamentals"] = fund
    _write_json(out_dir / "series.json", series)

    from analysis.signals import build_signal_records

    signals = build_signal_records(con)
    _write_json(out_dir / "signals.json", signals, default=str)

    tickers = sorted({t for n in nodes for t in n["tickers"]})
    stages = [
        "eda", "equipment", "foundry", "packaging", "chips",
        "networking", "grid", "power", "cloud",
    ]
    meta = {
        "generated_at": con.execute("SELECT now()").fetchone()[0].isoformat(),
        "schema_version": SCHEMA_VERSION, "tickers": tickers, "stages": stages,
    }
    _write_json(out_dir / "meta.json", meta, default=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    export_all(con, Path(args.out))
    con.close()
    print(f"export_data: wrote JSON to {args.out}")


if __name__ == "__main__":
    main()
