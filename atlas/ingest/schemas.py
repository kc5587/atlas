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
