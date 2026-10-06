-- Supply & operations: supplier economics, concentration risk, city health.


-- Q1 | Supplier concentration (Pareto) + economics
-- Business question: How dependent is the marketplace on its top suppliers
--   (concentration risk), and which suppliers drive the most take?
-- Technique: rank suppliers by GMV with a running cumulative share
--   (SUM() OVER ordered), flag the set that makes up the first 80% of GMV.
WITH sup AS (
    SELECT
        b.supplier_id,
        s.supplier_tier,
        ci.city,
        COUNT(*)                                       AS bookings,
        SUM(b.gbv_usd)                                 AS gmv,
        SUM(b.net_revenue_usd)                         AS net_revenue,
        AVG(b.commission_rate)                         AS avg_commission
    FROM fact_bookings b
    JOIN dim_supplier s ON s.supplier_id = b.supplier_id
    JOIN dim_city     ci ON ci.city_id    = s.city_id
    WHERE b.status <> 'cancelled'
    GROUP BY b.supplier_id, s.supplier_tier, ci.city
),
ranked AS (
    SELECT
        sup.*,
        ROW_NUMBER() OVER (ORDER BY gmv DESC)                              AS gmv_rank,
        ROUND(100.0 * SUM(gmv) OVER (ORDER BY gmv DESC
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
              / SUM(gmv) OVER (), 1)                                        AS running_gmv_share_pct
    FROM sup
)
SELECT
    gmv_rank,
    supplier_id,
    city,
    supplier_tier,
    bookings,
    ROUND(gmv, 0)                       AS gmv_usd,
    ROUND(net_revenue, 0)               AS net_revenue_usd,
    ROUND(100.0 * avg_commission, 1)    AS avg_take_rate_pct,
    running_gmv_share_pct,
    CASE WHEN running_gmv_share_pct <= 80 THEN 'Top 80% of GMV' ELSE 'Long tail' END AS tier_flag
FROM ranked
ORDER BY gmv_rank
LIMIT 25;


-- Q2 | City operational health scorecard
-- Business question: Which cities are healthy and which have operational
--   problems (high cancellations, weak ratings, thin supply)?
-- Technique: fact->dim JOINs with a correlated-style subquery for active supply,
--   multiple conditional/averaged metrics in one scorecard.
SELECT
    ci.city,
    ci.region,
    COUNT(*)                                                       AS bookings,
    ROUND(SUM(b.gbv_usd), 0)                                       AS gmv_usd,
    ROUND(100.0 * SUM(CASE WHEN b.status = 'cancelled' THEN 1 ELSE 0 END)
          / COUNT(*), 1)                                           AS cancellation_rate_pct,
    ROUND(AVG(b.rating), 2)                                        AS avg_rating,
    ROUND(AVG(b.lead_days), 1)                                     AS avg_lead_days,
    (SELECT COUNT(*) FROM dim_experience e WHERE e.city_id = ci.city_id) AS listed_experiences,
    COUNT(DISTINCT b.experience_id)                               AS experiences_sold
FROM fact_bookings b
JOIN dim_city ci ON ci.city_id = b.city_id
GROUP BY ci.city, ci.region, ci.city_id
ORDER BY gmv_usd DESC;
