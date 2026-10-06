-- A/B experiment mart (checkout_v2): per-arm conversion with absolute and
-- relative lift vs control. Point estimates; the p-value is computed in
-- python/03_analysis.py (two-proportion z-test).
with arm as (
    select
        experiment_group as variant,
        count(*)         as sessions,
        sum(is_booked)   as bookings,
        {{ safe_divide('sum(is_booked)', 'count(*)') }} as conv_rate
    from {{ ref('fct_sessions') }}
    where experiment_group in ('control', 'treatment')
    group by 1
),
ctrl as (select conv_rate as control_rate from arm where variant = 'control')
select
    a.variant,
    a.sessions,
    a.bookings,
    round(100.0 * a.conv_rate, 2)                                  as conversion_pct,
    round(100.0 * (a.conv_rate - c.control_rate), 2)               as abs_lift_pp,
    round(100.0 * (a.conv_rate - c.control_rate)
          / nullif(c.control_rate, 0), 1)                          as rel_lift_pct
from arm a
cross join ctrl c
order by a.variant
