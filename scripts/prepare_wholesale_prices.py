"""Normalise official EIA wholesale workbooks into Atlas CSV input."""

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frames = [pd.read_excel(path) for path in args.inputs]
    frame = pd.concat(frames, ignore_index=True)
    required = ("Price hub", "Delivery start date", "High price $/MWh")
    missing = tuple(column for column in required if column not in frame.columns)
    if missing:
        raise SystemExit(f"EIA workbook is missing columns: {', '.join(missing)}")
    normalized = frame.loc[:, list(required)].rename(
        columns={
            "Price hub": "Hub",
            "Delivery start date": "Date",
            "High price $/MWh": "High Price",
        }
    )
    normalized["Date"] = pd.to_datetime(normalized["Date"]).dt.date.astype(str)
    normalized = normalized.dropna(subset=["Hub", "Date", "High Price"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(args.output, index=False)
    print(f"{args.output} rows={len(normalized)}")


if __name__ == "__main__":
    main()
