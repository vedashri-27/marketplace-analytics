with source as (
    select * from {{ source('raw', 'dim_supplier') }}
)
select
    supplier_id,
    supplier_name,
    city_id,
    supplier_tier,
    commission_rate,
    cast(onboarded_date as date) as onboarded_date
from source
