-- Channel efficiency mart: the weekly growth-review table. One row per channel
-- with funnel, spend, CAC and ROAS, plus an action recommendation.
with sessions as (
    select channel, count(*) as sessions, sum(is_booked) as bookings
    from {{ ref('fct_sessions') }}
    group by 1
),
revenue as (
    select channel, sum(gbv_usd) as gmv, sum(net_revenue_usd) as net_revenue
    from {{ ref('fct_bookings') }}
    where not is_cancelled
    group by 1
),
spend as (
    select channel, sum(spend_usd) as spend
    from {{ ref('stg_marketing_spend') }}
    group by 1
)
select
    s.channel,
    s.sessions,
    s.bookings,
    round({{ safe_divide('s.bookings', 's.sessions') }} * 100, 2)        as conversion_pct,
    round(coalesce(m.spend, 0), 0)                                       as spend_usd,
    round(r.gmv, 0)                                                      as gmv_usd,
    round(r.net_revenue, 0)                                             as net_revenue_usd,
    case when m.spend > 0 then round({{ safe_divide('m.spend', 's.bookings') }}, 1) end      as cac_usd,
    case when m.spend > 0 then round({{ safe_divide('r.net_revenue', 'm.spend') }}, 2) end   as roas_on_net_rev,
    case when m.spend > 0 then round({{ safe_divide('r.gmv', 'm.spend') }}, 1) end           as roas_on_gmv,
    case
        when m.spend is null or m.spend = 0 then 'Organic / owned'
        when r.net_revenue / m.spend >= 1.5  then 'Scale'
        when r.net_revenue / m.spend >= 1.0  then 'Optimise'
        else 'Cut / fix'
    end                                                                 as recommendation
from sessions s
left join revenue r using (channel)
left join spend   m using (channel)
order by net_revenue_usd desc
