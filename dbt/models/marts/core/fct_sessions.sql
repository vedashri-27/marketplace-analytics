-- Session fact (grain: one row per session). Funnel flags exposed as 0/1 ints so
-- they SUM cleanly into funnel/conversion metrics downstream.
select
    session_id,
    session_date,
    customer_id,
    is_returning,
    channel,
    device,
    city_id,
    landing_experience_id,
    experiment_group,
    cast(stage_view     as int) as stage_view,
    cast(stage_cart     as int) as stage_cart,
    cast(stage_checkout as int) as stage_checkout,
    cast(converted      as int) as is_booked,
    booking_id
from {{ ref('stg_sessions') }}
