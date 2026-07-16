"""Download one public source artifact with an atomic local write."""

import argparse
from pathlib import Path
from urllib.request import Request, urlopen


def download(url: str, output: Path) -> None:
    """Download one public file using an atomic local write."""

    request = Request(url, headers={"User-Agent": "Atlas/0.1 public-data-fetch"})
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
            handle.write(response.read())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    download(args.url, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
