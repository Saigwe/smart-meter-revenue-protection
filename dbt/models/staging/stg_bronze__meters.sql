select
    meter_id,
    feeder_id,
    tariff_band
from {{ source('bronze', 'meters') }}
