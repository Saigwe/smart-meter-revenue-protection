-- Energy consumed vs energy bought per meter per week. A large positive gap suggests bypass or theft.
with consumed as (
    select meter_id, cast({{ dbt.date_trunc('week', 'reading_ts') }} as date) as week_start, sum(kwh) as consumed_kwh
    from {{ ref('stg_bronze__readings') }}
    group by 1, 2
),

purchased as (
    select meter_id, cast({{ dbt.date_trunc('week', 'vend_ts') }} as date) as week_start, sum(kwh_purchased) as purchased_kwh
    from {{ ref('stg_bronze__vends') }}
    group by 1, 2
)

select
    c.meter_id,
    m.feeder_id,
    c.week_start,
    c.consumed_kwh,
    coalesce(p.purchased_kwh, 0)                        as purchased_kwh,
    c.consumed_kwh - coalesce(p.purchased_kwh, 0)       as gap_kwh,
    rank() over (partition by m.feeder_id, c.week_start
                 order by c.consumed_kwh - coalesce(p.purchased_kwh, 0) desc) as gap_rank_in_feeder
from consumed c
join {{ ref('stg_bronze__meters') }} m on m.meter_id = c.meter_id
left join purchased p on p.meter_id = c.meter_id and p.week_start = c.week_start
