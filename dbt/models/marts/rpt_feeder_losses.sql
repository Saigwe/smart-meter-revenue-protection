-- Energy into each feeder vs energy its meters reported, per week. Technical losses are a few percent; the
-- excess over the feeder's own loss in the baseline window (the same season a year earlier) is the signal.
with weekly as (
    select
        s.feeder_id,
        cast(date_trunc('week', s.supply_date) as date)                         as week_start,
        sum(s.supply_kwh)                                                       as supply_kwh
    from {{ ref('stg_feeder_supply') }} s
    group by 1, 2
),
metered as (
    select feeder_id, week_start, sum(metered_kwh) as metered_kwh, count(distinct meter_id) as meters
    from {{ ref('fct_meter_weekly') }}
    group by 1, 2
),
losses as (
    select w.feeder_id, w.week_start, w.supply_kwh, m.metered_kwh, m.meters,
           (w.supply_kwh - m.metered_kwh) / nullif(w.supply_kwh, 0)                 as loss_share
    from weekly w join metered m using (feeder_id, week_start)
),
baseline as (
    select feeder_id, median(loss_share) as baseline_loss_share
    from losses
    where week_start between date '{{ var("baseline_start") }}' and date '{{ var("baseline_end") }}'
    group by 1
)
select
    l.*,
    b.baseline_loss_share,
    l.loss_share - b.baseline_loss_share                                        as excess_loss_share,
    (l.loss_share - b.baseline_loss_share) * l.supply_kwh                       as excess_loss_kwh
from losses l
left join baseline b using (feeder_id)
