select ticker, date, open, high, low, close, adj_close, volume
from {{ ref('stg_prices') }}
