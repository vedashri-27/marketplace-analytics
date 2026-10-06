with source as (
    select * from {{ source('raw', 'dim_city') }}
)
select
    city_id,
    city,
    country,
    region,
    currency,
    fx_local_per_usd,
    city_tier,
    popularity_weight,
    cast(launch_date as date) as launch_date
from source
