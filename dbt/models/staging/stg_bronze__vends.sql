select
    vend_id,
    meter_id,
    vend_ts,
    kwh_purchased
from {{ source('bronze', 'vends') }}
