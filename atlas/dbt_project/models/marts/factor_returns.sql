-- Daily log returns for factor ETFs only (SPY market, SOXX semis, IGV cloud).
-- Factors flow into stg_prices via the prices/*.parquet glob; this isolates them.
select ticker, date, log_return
from {{ ref('returns') }}
where ticker in ('SPY', 'SOXX', 'IGV')
