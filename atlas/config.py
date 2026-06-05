from __future__ import annotations

import os
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

# Layer 2: SEC EDGAR fundamentals.
SEC_USER_AGENT = os.getenv("ATLAS_SEC_USER_AGENT", "atlas-research atlas@example.com")
SEC_RATE_LIMIT_SECONDS = 0.2

CONCEPT_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
}

FUND_MAX_LAG_QUARTERS = 4
FUND_NMIN = 12

# H5 capex priced-in test: forward-return windows in trading days (~1Q, ~2Q).
H5_FORWARD_HORIZONS: tuple[int, ...] = (63, 126)

# H2 event-drift: forward drift horizons (trading days) and surprise lookback (quarters).
H2_DRIFT_HORIZONS: tuple[int, ...] = (21, 42, 63)
H2_SURPRISE_K = 4

# Priority 1 hardening: factor model + OOS params.
FACTOR_TICKERS: dict[str, str] = {"market": "SPY", "semis": "SOXX", "cloud": "IGV"}
STAGE_SECTOR: dict[str, str] = {
    "equipment": "semis", "foundry": "semis", "chips": "semis", "cloud": "cloud",
}
LAG_MIN = 1
LAG_MAX = MAX_LAG_DAYS  # one-sided, hypothesized direction only

OOS_TEST_DAYS = 252
OOS_STEP_DAYS = 252
OOS_INIT_TRAIN_FRAC = 0.5
OOS_EMBARGO_DAYS = MAX_LAG_DAYS
OOS_MIN_FOLDS = 3
OOS_SIGN_RATE_FLOOR = 0.6        # descriptive heuristic, NOT a significance test
LEAVE_ONE_OUT_WEIGHT = 0.10      # ETF-weight threshold for leave-one-out variant
