with q as (
    select ticker, period_end, filed, fy, fiscal_period, metric, value
    from {{ ref('stg_fundamentals') }}
    where fiscal_period in ('Q1', 'Q2', 'Q3', 'Q4')
)

select
    ticker,
    period_end,
    max(filed) as filed,
    any_value(fy) as fy,
    any_value(fiscal_period) as fiscal_period,
    max(case when metric = 'revenue' then value end) as revenue,
    max(case when metric = 'capex' then value end) as capex,
    max(case when metric = 'gross_margin' then value end) as gross_margin
from q
group by ticker, period_end
