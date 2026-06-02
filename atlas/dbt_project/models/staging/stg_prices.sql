with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/prices/*.parquet')
)
select
    cast(ticker as varchar)      as ticker,
    cast(date as date)           as date,
    cast(open as double)         as open,
    cast(high as double)         as high,
    cast(low as double)          as low,
    cast(close as double)        as close,
    cast(adj_close as double)    as adj_close,
    cast(volume as bigint)       as volume
from src
