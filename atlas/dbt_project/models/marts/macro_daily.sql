select series_id, date, value
from {{ ref('stg_macro') }}
