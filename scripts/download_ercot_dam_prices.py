"""Download official ERCOT annual day-ahead settlement-point-price archives."""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPORT_TYPE_ID = 13060
DOCUMENT_LIST_URL = (
    "https://www.ercot.com/misapp/servlets/IceDocListJsonWS"
)
DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload"
USER_AGENT = "Atlas/0.1 public-data-fetch"


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
        document = _find_document(year)
        target = args.output_dir / f"ercot_dam_spp_{year}.zip"
        _download(document, target)
        print(target)


def _find_document(year: int) -> str:
    query = urlencode({"reportTypeId": REPORT_TYPE_ID, "_": int(time.time())})
    request = Request(
        f"{DOCUMENT_LIST_URL}?{query}",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.ercot.com/mp/data-products/data-product-details?id=np4-180-er",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise RuntimeError("could not read the ERCOT document list") from error
    documents = payload.get("ListDocsByRptTypeRes", {}).get("DocumentList", [])
    for document in documents:
        details = document.get("Document", document)
        name = str(details.get("ConstructedName", ""))
        if f"{year}.zip" in name:
            document_id = details.get("DocID")
            if document_id:
                return f"{DOWNLOAD_URL}?doclookupId={document_id}"
    raise RuntimeError(f"ERCOT report {year} archive was not found")


def _download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
            handle.write(response.read())
        temporary.replace(target)
    except (HTTPError, URLError, OSError) as error:
        raise RuntimeError(f"could not download ERCOT archive: {url}") from error
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
