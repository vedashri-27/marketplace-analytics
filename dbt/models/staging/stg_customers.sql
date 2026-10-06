with source as (
    select * from {{ source('raw', 'dim_customer') }}
)
select
    customer_id,
    cast(signup_date as date) as signup_date,
    acquisition_channel,
    country,
    signup_device
from source
