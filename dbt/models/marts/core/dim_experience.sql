-- Conformed experience dimension: experience enriched with its supplier and
-- city attributes so downstream marts never need to re-join.
with e as (select * from {{ ref('stg_experiences') }}),
     s as (select * from {{ ref('stg_suppliers') }}),
     c as (select * from {{ ref('stg_cities') }})
select
    e.experience_id,
    e.experience_name,
    e.category,
    e.base_price_usd,
    e.duration_hours,
    e.max_group_size,
    e.popularity,
    e.listed_date,
    -- city attributes
    e.city_id,
    c.city,
    c.region,
    c.country,
    c.currency,
    c.city_tier,
    -- supplier attributes
    e.supplier_id,
    s.supplier_name,
    s.supplier_tier,
    s.commission_rate
from e
left join s on s.supplier_id = e.supplier_id
left join c on c.city_id = e.city_id
