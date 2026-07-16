"""Download official EIA-930 six-month balance files."""

import argparse
from pathlib import Path

from download_public_file import download


BASE_URL = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("start-year must not be after end-year")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year in range(args.start_year, args.end_year + 1):
        for half in ("Jan_Jun", "Jul_Dec"):
            name = f"EIA930_BALANCE_{year}_{half}.csv"
            target = args.output_dir / name
            download(f"{BASE_URL}{name}", target)
            print(target)


if __name__ == "__main__":
    main()
