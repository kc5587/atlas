select series, date, close
from {{ ref('stg_vol') }}
