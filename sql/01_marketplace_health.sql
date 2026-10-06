-- Marketplace health: monthly KPIs + where GMV comes from.
-- Written for SQLite (the repo ships a SQLite db). On Postgres/Snowflake,
-- swap strftime('%Y-%m', d) for to_char(d,'YYYY-MM') or date_trunc('month', d).


-- Q1 | Monthly marketplace KPIs with month-over-month growth
-- Business question: How is the marketplace trending month over month on the
--   metrics leadership actually watches — GMV, net revenue, bookings, AOV, take
--   rate — and is growth accelerating or decelerating?
-- Technique: CTE, date bucketing, LAG() window for MoM deltas, safe division.
WITH monthly AS (
    SELECT
        strftime('%Y-%m', booking_date)                       AS year_month,
        COUNT(*)                                              AS bookings,
        SUM(gbv_usd)                                          AS gmv,
        SUM(net_revenue_usd)                                  AS net_revenue,
        SUM(num_guests)                                       AS guests
    FROM fact_bookings
    WHERE status <> 'cancelled'                 -- realised demand only
    GROUP BY 1
)
SELECT
    year_month,
    bookings,
    ROUND(gmv, 0)                                             AS gmv_usd,
    ROUND(net_revenue, 0)                                     AS net_revenue_usd,
    ROUND(gmv / bookings, 1)                                  AS aov_usd,
    ROUND(100.0 * net_revenue / gmv, 1)                       AS take_rate_pct,
    -- month-over-month GMV growth using the previous row
    ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY year_month))
          / NULLIF(LAG(gmv) OVER (ORDER BY year_month), 0), 1) AS gmv_mom_growth_pct
FROM monthly
ORDER BY year_month;


-- Q2 | Region & city-tier contribution with running share of GMV
-- Business question: Which regions and city tiers carry the marketplace, and
--   how concentrated is GMV geographically?
-- Technique: multi-table JOIN, GROUP BY rollup-style, SUM() OVER for a running
--   cumulative share (a Pareto view of geography).
WITH geo AS (
    SELECT
        ci.region,
        ci.city_tier,
        SUM(b.gbv_usd)            AS gmv,
        SUM(b.net_revenue_usd)    AS net_revenue,
        COUNT(*)                  AS bookings
    FROM fact_bookings b
    JOIN dim_city ci ON ci.city_id = b.city_id
    WHERE b.status <> 'cancelled'
    GROUP BY ci.region, ci.city_tier
)
SELECT
    region,
    city_tier,
    bookings,
    ROUND(gmv, 0)                                               AS gmv_usd,
    ROUND(100.0 * gmv / SUM(gmv) OVER (), 1)                    AS pct_of_total_gmv,
    ROUND(100.0 * SUM(gmv) OVER (ORDER BY gmv DESC)
          / SUM(gmv) OVER (), 1)                                AS running_pct_of_gmv
FROM geo
ORDER BY gmv DESC;
