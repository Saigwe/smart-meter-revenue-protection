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
stepped as (
    -- An abrupt, lasting step: over the year before the evaluation window, the week where the next six weeks'
    -- average falls furthest below the previous six weeks'. Tampering changes use within a week and stays changed;
    -- most real changes are gradual. Night-time share is stepped the same way.
    select
        meter_id, feeder_id, week_start,
        avg(metered_kwh) over w_before                                          as before_kwh,
        avg(metered_kwh) over w_after                                           as after_kwh,
        avg(metered_night_kwh / nullif(metered_kwh, 0)) over w_before           as before_night,
        avg(metered_night_kwh / nullif(metered_kwh, 0)) over w_after            as after_night,
        count(*) over w_before                                                  as n_before,
        count(*) over w_after                                                   as n_after
    from {{ ref('fct_meter_weekly') }}
    where week_start between date '{{ b1 }}' - interval 12 week and date '{{ e1 }}'
    window w_before as (partition by meter_id order by week_start rows between 6 preceding and 1 preceding),
           w_after as (partition by meter_id order by week_start rows between current row and 5 following)
),
steps as (
    select
        meter_id,
        any_value(feeder_id)                                                    as feeder_id,
        min(after_kwh / nullif(before_kwh, 0))                                  as step_ratio,
        arg_min(week_start, after_kwh / nullif(before_kwh, 0))                  as step_week,
        arg_min(before_kwh - after_kwh, after_kwh / nullif(before_kwh, 0))      as step_drop_kwh_per_week,
        min(after_night / nullif(before_night, 0))                              as night_step_ratio
    from stepped
    where n_before = 6 and n_after = 6
    group by 1
),
feeder_weekly_loss as (
    select feeder_id, week_start, supply_kwh - metered_kwh as loss_kwh from {{ ref('rpt_feeder_losses') }}
),
confirmed as (
    -- ENERGY BALANCE: with a bypass the energy still flows through the feeder, so the feeder's losses jump by
    -- about what the meter stopped recording, in the same week. A household that really used less leaves the
    -- feeder's losses unchanged. confirmation = feeder loss jump / meter drop (~1 for theft, ~0 for a real drop).
    select
        s.meter_id,
        (avg(l.loss_kwh) filter (where l.week_start between s.step_week and s.step_week + interval 5 week)
         - avg(l.loss_kwh) filter (where l.week_start between s.step_week - interval 6 week and s.step_week - interval 1 week))
            / nullif(any_value(s.step_drop_kwh_per_week), 0)                    as feeder_confirmation
    from steps s
    join feeder_weekly_loss l on l.feeder_id = s.feeder_id
     and l.week_start between s.step_week - interval 6 week and s.step_week + interval 5 week
    group by 1
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
    st.step_ratio,
    st.night_step_ratio,
    st.step_week,
    st.step_drop_kwh_per_week,
    c.feeder_confirmation,
    r.consumption_ratio / nullif(f.feeder_median_ratio, 0)                      as consumption_ratio_vs_feeder,
    r.eval_night_share / nullif(r.base_night_share, 0)                          as night_share_ratio,
    f.feeder_excess_loss_share
from rated r
join feeder f using (feeder_id)
left join steps st using (meter_id)
left join confirmed c using (meter_id)
