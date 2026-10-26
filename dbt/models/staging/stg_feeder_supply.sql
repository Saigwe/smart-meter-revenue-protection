select feeder_id, cast(supply_date as date) as supply_date, cast(supply_kwh as double) as supply_kwh
from {{ source('lake', 'sim_feeder_supply') }}
