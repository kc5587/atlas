from __future__ import annotations

import pandera.pandas as pa

PRICE_SCHEMA = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "open": pa.Column(float, pa.Check.ge(0), nullable=True),
        "high": pa.Column(float, pa.Check.ge(0), nullable=True),
        "low": pa.Column(float, pa.Check.ge(0), nullable=True),
        "close": pa.Column(float, pa.Check.ge(0), nullable=False),
        "adj_close": pa.Column(float, pa.Check.ge(0), nullable=False),
        "volume": pa.Column("int64", pa.Check.ge(0), nullable=True, coerce=True),
    },
    strict=True,
)

MACRO_SCHEMA = pa.DataFrameSchema(
    {
        "series_id": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "value": pa.Column(float, nullable=False),
    },
    strict=True,
)

VOL_SCHEMA = pa.DataFrameSchema(
    {
        "series": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "close": pa.Column(float, pa.Check.ge(0), nullable=False),
    },
    strict=True,
)

IV_SNAPSHOT_SCHEMA = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "atm_iv_30d": pa.Column(float, pa.Check.ge(0), nullable=True),
        "skew_25d": pa.Column(float, nullable=True),
        "term_slope": pa.Column(float, nullable=True),
        "put_call_oi": pa.Column(float, pa.Check.ge(0), nullable=True),
    },
    strict=True,
)

FUNDAMENTAL_SCHEMA = pa.DataFrameSchema(
    {
        "cik": pa.Column(str, nullable=False),
        "ticker": pa.Column(str, nullable=False),
        "concept": pa.Column(str, nullable=False),
        "metric": pa.Column(str, pa.Check.isin(["revenue", "capex", "gross_margin"])),
        "period_start": pa.Column("datetime64[ns]", nullable=True),
        "period_end": pa.Column("datetime64[ns]", nullable=False),
        "filed": pa.Column("datetime64[ns]", nullable=False),
        "fiscal_period": pa.Column(str, nullable=True),
        "fy": pa.Column("int64", nullable=True, coerce=True),
        "form": pa.Column(str, nullable=True),
        "value": pa.Column(float, nullable=False),
        "unit": pa.Column(str, nullable=False),
        "accn": pa.Column(str, nullable=False),
    },
    strict=True,
)
