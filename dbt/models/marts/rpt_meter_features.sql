-- One row per meter reporting in both windows: the evaluation window (Oct-Dec 2013) against the baseline (the
-- same weeks of 2012). Ratios are also taken against the feeder's median, so a cold winter or a tariff trial that
-- moves everyone doesn't look like theft. Detection features only: no ground truth, no real (unmetered) use.
{% set b0, b1, e0, e1 = var('baseline_start'), var('baseline_end'), var('eval_start'), var('eval_end') %}
with win as (
    select
        meter_id,
        any_value(feeder_id)                                                    as feeder_id,
        any_value(tariff_group)                                                 as tariff_group,
        sum(metered_kwh) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}')
            / nullif(sum(days_reported) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}'), 0) as base_kwh_per_day,
        sum(metered_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}')
            / nullif(sum(days_reported) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}'), 0) as eval_kwh_per_day,
        sum(metered_night_kwh) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}')
            / nullif(sum(metered_kwh) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}'), 0) as base_night_share,
        sum(metered_night_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}')
            / nullif(sum(metered_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}'), 0) as eval_night_share,
        sum(purchased_kwh) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}')
            / nullif(sum(metered_kwh) filter (where week_start between date '{{ b0 }}' and date '{{ b1 }}'), 0) as base_purchase_ratio,
        sum(purchased_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}')
            / nullif(sum(metered_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}'), 0) as eval_purchase_ratio,
        sum(flat_days) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}') * 1.0
            / nullif(sum(days_reported) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}'), 0) as eval_flat_day_share,
        sum(metered_kwh - purchased_kwh) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}')
            / nullif(sum(days_reported) filter (where week_start between date '{{ e0 }}' and date '{{ e1 }}'), 0) as eval_gap_kwh_per_day
    from {{ ref('fct_meter_weekly') }}
    group by meter_id
),
rated as (
    select *, eval_kwh_per_day / nullif(base_kwh_per_day, 0) as consumption_ratio
    from win
    where base_kwh_per_day > 0 and eval_kwh_per_day is not null
),
feeder as (
    select
        r.feeder_id,
        median(r.consumption_ratio)                                             as feeder_median_ratio,
        any_value(f.excess_loss_share)                                          as feeder_excess_loss_share
    from rated r
    left join (
        select feeder_id, avg(excess_loss_share) as excess_loss_share
        from {{ ref('rpt_feeder_losses') }}
        where week_start between date '{{ e0 }}' and date '{{ e1 }}'
        group by 1
    ) f using (feeder_id)
    group by 1
)
select
    r.*,
    r.consumption_ratio / nullif(f.feeder_median_ratio, 0)                      as consumption_ratio_vs_feeder,
    r.eval_night_share / nullif(r.base_night_share, 0)                          as night_share_ratio,
    f.feeder_excess_loss_share
from rated r
join feeder f using (feeder_id)
