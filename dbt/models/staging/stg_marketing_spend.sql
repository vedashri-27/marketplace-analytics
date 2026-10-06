with source as (
    select * from {{ source('raw', 'fact_marketing_spend') }}
)
select
    cast(spend_date as date) as spend_date,
    channel,
    city_id,
    impressions,
    clicks,
    spend_usd
from source
