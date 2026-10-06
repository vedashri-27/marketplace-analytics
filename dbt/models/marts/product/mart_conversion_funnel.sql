-- Conversion funnel mart: tidy stage table with step conversion and drop-off,
-- ready to drop straight onto a dashboard.
with f as (
    select
        count(*)              as sessions,
        sum(stage_view)       as viewed,
        sum(stage_cart)       as added_to_cart,
        sum(stage_checkout)   as checkout_started,
        sum(is_booked)        as booked
    from {{ ref('fct_sessions') }}
),
stages as (
    select 1 as step_no, 'Session'           as stage, sessions         as users from f
    union all select 2, 'Viewed experience',  viewed           from f
    union all select 3, 'Added to cart',      added_to_cart    from f
    union all select 4, 'Checkout started',   checkout_started from f
    union all select 5, 'Booked',             booked           from f
)
select
    step_no,
    stage,
    users,
    round(100.0 * users / first_value(users) over (order by step_no), 1) as pct_of_sessions,
    round(100.0 * users / lag(users) over (order by step_no), 1)         as step_conversion_pct,
    lag(users) over (order by step_no) - users                          as users_lost_vs_prev
from stages
order by step_no
