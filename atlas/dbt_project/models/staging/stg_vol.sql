with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/vol/*.parquet')
)
select
    cast(series as varchar) as series,
    cast(date as date)      as date,
    cast(close as double)   as close
from src
where close is not null
