with source as (
    select * from {{ source('raw', 'fact_bookings') }}
)
select
    booking_id,
    session_id,
    customer_id,
    experience_id,
    supplier_id,
    city_id,
    cast(booking_date as date)              as booking_date,
    cast(travel_date  as date)              as travel_date,
    lead_days,
    num_guests,
    currency,
    fx_local_per_usd,
    base_price_usd,
    price_multiplier,
    effective_price_usd,
    discount_usd,
    gbv_usd,
    gbv_local,
    commission_rate,
    net_revenue_usd,
    supplier_payout_usd,
    channel,
    device,
    experiment_group,
    status,
    rating,
    (status = 'cancelled')                  as is_cancelled
from source
