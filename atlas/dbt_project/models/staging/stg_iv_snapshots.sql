with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/iv_snapshots/*.parquet')
)
select
    cast(ticker as varchar)      as ticker,
    cast(date as date)           as date,
    cast(atm_iv_30d as double)   as atm_iv_30d,
    cast(skew_25d as double)     as skew_25d,
    cast(term_slope as double)   as term_slope,
    cast(put_call_oi as double)  as put_call_oi
from src
