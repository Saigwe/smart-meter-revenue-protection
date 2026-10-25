select * from {{ ref('rpt_meter_weekly_gap') }} where consumed_kwh < 0 or purchased_kwh < 0
