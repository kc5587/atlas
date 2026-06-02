with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/macro/*.parquet')
)
select
    cast(series_id as varchar) as series_id,
    cast(date as date)         as date,
    cast(value as double)      as value
from src
