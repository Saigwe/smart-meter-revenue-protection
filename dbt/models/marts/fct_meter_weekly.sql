-- One row per meter per week: what the meter reported, what the customer bought, and the gap between them.
-- Reads metered data, vends and meters only: what a utility actually has.
with days as (
    select d.*, m.feeder_id
    from {{ ref('sim_meter_daily_metered') }} d
    join {{ ref('stg_meters') }} m using (meter_id)
),
weekly as (
    select
        meter_id,
        any_value(feeder_id)                                                    as feeder_id,
        any_value(tariff_group)                                                 as tariff_group,
        cast(date_trunc('week', reading_date) as date)                          as week_start,
        count(*)                                                                as days_reported,
        sum(readings)                                                           as readings,
        sum(metered_kwh)                                                        as metered_kwh,
        sum(metered_night_kwh)                                                  as metered_night_kwh,
        count(*) filter (where distinct_values <= 2 and readings >= 40)         as flat_days
    from days
    group by meter_id, week_start
),
bought as (
    select meter_id, cast(date_trunc('week', vend_date) as date) as week_start, sum(kwh) as purchased_kwh,
           sum(amount_gbp) as purchased_gbp, count(*) as vends
    from {{ ref('stg_vends') }}
    group by 1, 2
)
select
    w.*,
    coalesce(b.purchased_kwh, 0)                                                as purchased_kwh,
    coalesce(b.purchased_gbp, 0)                                                as purchased_gbp,
    coalesce(b.vends, 0)                                                        as vends,
    w.metered_kwh - coalesce(b.purchased_kwh, 0)                                as gap_kwh
from weekly w
left join bought b using (meter_id, week_start)
