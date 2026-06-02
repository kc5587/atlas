with p as (
    select ticker, date, adj_close,
           lag(adj_close) over (partition by ticker order by date) as prev_adj_close
    from {{ ref('stg_prices') }}
)
select ticker, date, ln(adj_close / prev_adj_close) as log_return
from p
where prev_adj_close is not null and prev_adj_close > 0
