-- The household's real use per day (the Low Carbon London readings as delivered). Used ONLY to evaluate
-- revenue-at-risk estimates and to reconcile the lake; detection never reads it (lineage-tested).
select
    meter_id,
    reading_date,
    count(*)                                                        as readings,
    sum(kwh)                                                        as true_kwh
from {{ source('lake', 'readings') }}
group by 1, 2
