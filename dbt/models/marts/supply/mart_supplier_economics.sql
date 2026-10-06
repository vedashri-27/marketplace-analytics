-- Supplier economics + concentration (Pareto). One row per supplier with GMV,
-- take, and a running cumulative GMV share to size concentration risk.
with sup as (
    select
        b.supplier_id,
        de.supplier_tier,
        de.city,
        count(*)                   as bookings,
        sum(b.gbv_usd)             as gmv,
        sum(b.net_revenue_usd)     as net_revenue,
        avg(b.commission_rate)     as avg_commission
    from {{ ref('fct_bookings') }} b
    left join {{ ref('dim_experience') }} de on de.experience_id = b.experience_id
    where not b.is_cancelled
    group by 1, 2, 3
)
select
    row_number() over (order by gmv desc)                                        as gmv_rank,
    supplier_id,
    city,
    supplier_tier,
    bookings,
    round(gmv, 0)                                                                as gmv_usd,
    round(net_revenue, 0)                                                        as net_revenue_usd,
    round(100.0 * avg_commission, 1)                                            as avg_take_rate_pct,
    round(100.0 * sum(gmv) over (order by gmv desc
          rows between unbounded preceding and current row)
          / sum(gmv) over (), 1)                                                 as running_gmv_share_pct
from sup
order by gmv_rank
