select
    meter_id,
    reading_ts,
    kwh
from {{ source('bronze', 'readings') }}
