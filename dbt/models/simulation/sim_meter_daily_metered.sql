-- THE PHYSICAL WORLD -> WHAT THE METER REPORTS. The real half-hourly readings are the household's true use; a
-- tampered meter reports less from its start date (sim_tamper). This is the only model where the ground truth
-- touches the data, and its output carries metered values only:
--   bypass        reports factor x real use        flatline      reports a constant low value
--   night_bypass  reports nothing 00:00-06:00      credit_tamper reports honestly (the fraud is in the vends)
-- Aggregated to meter-days here, so detection never scans 168M rows again.
with metered as (
    select
        r.meter_id,
        r.tariff,
        r.reading_date,
        r.reading_ts,
        case
            when t.start_date is null or r.reading_date < t.start_date then r.kwh
            when t.tamper_type = 'bypass' then r.kwh * t.factor
            when t.tamper_type = 'flatline' then t.flat_kwh
            when t.tamper_type = 'night_bypass' and hour(r.reading_ts) < 6 then 0
            else r.kwh
        end as kwh
    from {{ source('lake', 'readings') }} r
    left join {{ source('lake', 'sim_tamper') }} t using (meter_id)
)
select
    meter_id,
    reading_date,
    any_value(tariff)                                               as tariff_group,
    count(*)                                                        as readings,
    sum(kwh)                                                        as metered_kwh,
    sum(kwh) filter (where hour(reading_ts) < 6)                    as metered_night_kwh,
    count(distinct round(kwh, 3))                                   as distinct_values
from metered
group by 1, 2
