"""Download monthly NYISO day-ahead zonal LBMP archives."""

import argparse
from calendar import monthrange
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://mis.nyiso.com/public/csv/damlbmp/{stamp}damlbmp_zone_csv.zip"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.start > args.end:
        raise SystemExit("start must not be after end")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year, month in _months(args.start, args.end):
        stamp = f"{year:04d}{month:02d}01"
        target = args.output_dir / f"{stamp}damlbmp_zone_csv.zip"
        _download(BASE_URL.format(stamp=stamp), target)
        print(target)


def _download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "Atlas/0.1 public-data-fetch"})
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
            handle.write(response.read())
        temporary.replace(target)
    except (HTTPError, URLError, OSError) as error:
        raise RuntimeError(f"could not download NYISO archive: {url}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _months(start: date, end: date) -> tuple[tuple[int, int], ...]:
    values: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        values.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(values)


if __name__ == "__main__":
    main()
