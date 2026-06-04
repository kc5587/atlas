select id, name, tickers, stage, region, cik
from {{ source('graph', 'graph_nodes') }}
