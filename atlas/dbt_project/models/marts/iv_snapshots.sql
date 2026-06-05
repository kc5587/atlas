select ticker, date, atm_iv_30d, skew_25d, term_slope, put_call_oi
from {{ ref('stg_iv_snapshots') }}
