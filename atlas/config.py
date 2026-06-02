from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_RAW = ROOT / "data" / "raw"
DUCKDB_PATH = ROOT / "data" / "atlas.duckdb"
SEED_PATH = ROOT / "seeds" / "value_chain.yml"

# Core spine universe (curated; extend in value_chain.yml too).
UNIVERSE: list[str] = [
    "ASML", "TSM", "NVDA", "AMD", "AVGO", "MU", "AMAT", "LRCX",
    "MSFT", "GOOGL", "AMZN", "META", "ORCL", "DELL", "SMCI",
]

# FRED series id -> human label. Native frequency handled at analysis time.
FRED_SERIES: dict[str, str] = {
    "DFF": "Effective Fed Funds Rate",
    "DGS10": "10Y Treasury Yield",
    "IPG3344S": "Semiconductor & Components IP Index",
}

PRICE_START = "2010-01-01"

# Lead/lag analysis windows.
MAX_LAG_DAYS = 20
PRICE_NMIN = 250
MACRO_NMIN = 36
TRAILING_YEARS = 3
BOOTSTRAP_ITERS = 1000
BOOTSTRAP_BLOCK = 20
FDR_ALPHA = 0.10
RANDOM_SEED = 7
