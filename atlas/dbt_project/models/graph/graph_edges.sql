select from_id, to_id, relationship, note, evidence, as_of
from {{ source('graph', 'graph_edges') }}
