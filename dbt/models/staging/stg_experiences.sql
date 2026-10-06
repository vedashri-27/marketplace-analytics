with source as (
    select * from {{ source('raw', 'dim_experience') }}
)
select
    experience_id,
    experience_name,
    city_id,
    supplier_id,
    category,
    base_price_usd,
    duration_hours,
    max_group_size,
    popularity,
    cast(listed_date as date) as listed_date
from source
