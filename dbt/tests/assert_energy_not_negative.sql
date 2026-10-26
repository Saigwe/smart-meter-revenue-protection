-- No negative energy anywhere: metered days, real days, vends or feeder supply.
select 'metered' as source, meter_id as id from {{ ref('sim_meter_daily_metered') }} where metered_kwh < 0
union all select 'truth', meter_id from {{ ref('sim_meter_daily_truth') }} where true_kwh < 0
union all select 'vend', vend_id from {{ ref('stg_vends') }} where kwh <= 0 or amount_gbp <= 0
union all select 'supply', feeder_id from {{ ref('stg_feeder_supply') }} where supply_kwh < 0
