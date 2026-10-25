select
    feeder_id,
    week_start,
    sum(consumed_kwh)                                                       as consumed_kwh,
    sum(purchased_kwh)                                                      as purchased_kwh,
    100.0 * (sum(consumed_kwh) - sum(purchased_kwh)) / nullif(sum(consumed_kwh), 0) as unbilled_pct
from {{ ref('rpt_meter_weekly_gap') }}
group by 1, 2
