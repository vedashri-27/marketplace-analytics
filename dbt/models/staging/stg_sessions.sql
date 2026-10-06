with source as (
    select * from {{ source('raw', 'fact_sessions') }}
)
select
    session_id,
    cast(session_date as date)      as session_date,
    customer_id,
    cast(is_returning as boolean)   as is_returning,
    channel,
    device,
    city_id,
    landing_experience_id,
    experiment_group,
    cast(stage_view     as boolean) as stage_view,
    cast(stage_cart     as boolean) as stage_cart,
    cast(stage_checkout as boolean) as stage_checkout,
    cast(converted      as boolean) as converted,
    booking_id
from source
