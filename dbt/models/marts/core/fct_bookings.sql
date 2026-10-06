-- Booking fact (grain: one row per booking). Keeps all measures and FKs, plus a
-- few denormalised attributes (category, region) that almost every query needs.
with b as (select * from {{ ref('stg_bookings') }}),
     e as (select experience_id, category from {{ ref('stg_experiences') }}),
     c as (select city_id, city, region from {{ ref('stg_cities') }})
select
    b.booking_id,
    b.session_id,
    b.customer_id,
    b.experience_id,
    e.category,
    b.supplier_id,
    b.city_id,
    c.city,
    c.region,
    b.booking_date,
    b.travel_date,
    b.lead_days,
    b.num_guests,
    b.channel,
    b.device,
    b.experiment_group,
    b.currency,
    b.base_price_usd,
    b.price_multiplier,
    b.effective_price_usd,
    b.discount_usd,
    b.gbv_usd,
    b.gbv_local,
    b.commission_rate,
    b.net_revenue_usd,
    b.supplier_payout_usd,
    b.status,
    b.is_cancelled,
    b.rating,
    -- incremental GMV captured by dynamic pricing on this booking
    (b.effective_price_usd - b.base_price_usd) * b.num_guests as dynamic_pricing_uplift_usd
from b
left join e on e.experience_id = b.experience_id
left join c on c.city_id = b.city_id
