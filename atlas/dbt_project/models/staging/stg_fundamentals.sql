with src as (
    select *
    from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/fundamentals/*.parquet')
)

select
    cast(cik as varchar) as cik,
    cast(ticker as varchar) as ticker,
    cast(metric as varchar) as metric,
    cast(period_end as date) as period_end,
    cast(filed as date) as filed,
    cast(fy as integer) as fy,
    cast(fiscal_period as varchar) as fiscal_period,
    cast(form as varchar) as form,
    cast(value as double) as value,
    cast(accn as varchar) as accn
from src
