select vend_id, meter_id, cast(vend_ts as timestamp) as vend_ts, cast(vend_ts as date) as vend_date,
       cast(amount_gbp as double) as amount_gbp, cast(kwh as double) as kwh
from {{ source('lake', 'sim_vends') }}
