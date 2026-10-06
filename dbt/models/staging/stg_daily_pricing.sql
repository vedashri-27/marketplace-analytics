with source as (
    select * from {{ source('raw', 'fact_daily_pricing') }}
)
select
    experience_id,
    cast(price_date as date) as price_date,
    base_price_usd,
    dynamic_price_usd,
    demand_index,
    slots_available,
    slots_booked
from source
