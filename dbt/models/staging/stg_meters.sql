select meter_id, feeder_id, cast(tariff_p_per_kwh as double) as tariff_p_per_kwh
from {{ source('lake', 'sim_meters') }}
