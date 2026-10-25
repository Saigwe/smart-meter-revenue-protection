select
    feeder_id,
    substation
from {{ source('bronze', 'feeders') }}
