-- Every real reading reaches the daily truth table, and untampered meters report exactly their real use.
with lake as (select count(*) as n, sum(kwh) as kwh from {{ source('lake', 'readings') }}),
truth as (select sum(readings) as n, sum(true_kwh) as kwh from {{ ref('sim_meter_daily_truth') }}),
honest as (
    select sum(abs(m.metered_kwh - t.true_kwh)) as diff
    from {{ ref('sim_meter_daily_metered') }} m
    join {{ ref('sim_meter_daily_truth') }} t using (meter_id, reading_date)
    where m.meter_id not in (select meter_id from {{ source('lake', 'sim_tamper') }})
)
select 'readings lost' as problem from lake, truth where lake.n <> truth.n or abs(lake.kwh - truth.kwh) > 0.01
union all
select 'honest meter misreported' from honest where diff > 0.01
