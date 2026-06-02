select id, name, tickers, stage, region
from {{ source('graph', 'graph_nodes') }}
