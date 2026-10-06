-- Growth & marketing: channel ROAS/CAC, acquisition-channel LTV, cohort retention.


-- Q1 | Channel performance: funnel, CAC and ROAS (last-touch)
-- Business question: Which paid channels are profitable and which are burning
--   money? Where should the next marketing dollar go?
-- Technique: two independent aggregations (sessions+bookings vs spend) stitched
--   with a LEFT JOIN, conversion/CAC/ROAS derived, ranked. This is the query a
--   growth team would run weekly.
WITH session_perf AS (
    SELECT
        s.channel,
        COUNT(*)                                   AS sessions,
        SUM(s.converted)                           AS bookings
    FROM fact_sessions s
    GROUP BY s.channel
),
revenue AS (
    SELECT
        b.channel,
        SUM(b.gbv_usd)                             AS gmv,
        SUM(b.net_revenue_usd)                     AS net_revenue
    FROM fact_bookings b
    WHERE b.status <> 'cancelled'
    GROUP BY b.channel
),
spend AS (
    SELECT channel, SUM(spend_usd) AS spend
    FROM fact_marketing_spend
    GROUP BY channel
)
SELECT
    sp.channel,
    sp.sessions,
    sp.bookings,
    ROUND(100.0 * sp.bookings / sp.sessions, 2)                 AS conversion_pct,
    ROUND(COALESCE(m.spend, 0), 0)                              AS spend_usd,
    ROUND(r.gmv, 0)                                             AS gmv_usd,
    ROUND(r.net_revenue, 0)                                     AS net_revenue_usd,
    -- CAC is only meaningful where we actually pay for traffic
    CASE WHEN m.spend > 0
         THEN ROUND(m.spend / NULLIF(sp.bookings, 0), 1) END    AS cac_usd,
    CASE WHEN m.spend > 0
         THEN ROUND(r.net_revenue / m.spend, 2) END             AS roas_on_net_rev,
    CASE WHEN m.spend > 0
         THEN ROUND(r.gmv / m.spend, 1) END                     AS roas_on_gmv,
    CASE
        WHEN m.spend IS NULL OR m.spend = 0 THEN 'Organic / owned'
        WHEN r.net_revenue / m.spend >= 1.5  THEN 'Scale'
        WHEN r.net_revenue / m.spend >= 1.0  THEN 'Optimise'
        ELSE 'Cut / fix'
    END                                                         AS recommendation
FROM session_perf sp
LEFT JOIN revenue r ON r.channel = sp.channel
LEFT JOIN spend   m ON m.channel = sp.channel
ORDER BY net_revenue_usd DESC;


-- Q2 | Acquisition-channel LTV (first-touch), 90-day realised value
-- Business question: Beyond first-order CAC, which channels bring customers who
--   are actually worth more over their first 90 days?
-- Technique: ROW_NUMBER() to find each customer's first booking, a self-style
--   JOIN back to all bookings within a 90-day window, GROUP BY acquisition
--   channel. Blends dimension + fact grain.
WITH first_booking AS (
    SELECT
        customer_id,
        booking_date AS first_date,
        ROW_NUMBER() OVER (PARTITION BY customer_id
                           ORDER BY booking_date, booking_id) AS rn
    FROM fact_bookings
    WHERE status <> 'cancelled' AND customer_id > 0
),
cohort AS (
    SELECT fb.customer_id, fb.first_date, c.acquisition_channel
    FROM first_booking fb
    JOIN dim_customer c ON c.customer_id = fb.customer_id
    WHERE fb.rn = 1
),
value_90d AS (
    SELECT
        co.acquisition_channel,
        co.customer_id,
        SUM(CASE WHEN b.booking_date <= date(co.first_date, '+90 day')
                 THEN b.net_revenue_usd ELSE 0 END) AS net_rev_90d
    FROM cohort co
    JOIN fact_bookings b
      ON b.customer_id = co.customer_id AND b.status <> 'cancelled'
    GROUP BY co.acquisition_channel, co.customer_id
)
SELECT
    acquisition_channel,
    COUNT(*)                               AS customers_acquired,
    ROUND(AVG(net_rev_90d), 1)             AS avg_90d_net_rev_usd,
    ROUND(SUM(net_rev_90d), 0)             AS total_90d_net_rev_usd
FROM value_90d
GROUP BY acquisition_channel
ORDER BY avg_90d_net_rev_usd DESC;


-- Q3 | Monthly signup-cohort retention (repeat-purchase curve)
-- Business question: Do customers come back? What share of each signup cohort
--   books again in months 1..6 after signup?
-- Technique: compute an integer "months since signup" from calendar parts, size
--   each cohort once, then conditional aggregation + window share to build a
--   retention triangle. Core product/growth analysis.
WITH cohort_size AS (
    SELECT strftime('%Y-%m', signup_date) AS cohort_month,
           COUNT(*)                        AS cohort_customers
    FROM dim_customer
    GROUP BY 1
),
booking_month AS (
    SELECT
        c.customer_id,
        strftime('%Y-%m', c.signup_date)                                    AS cohort_month,
        ( (CAST(strftime('%Y', b.booking_date) AS INT) * 12
           + CAST(strftime('%m', b.booking_date) AS INT))
        - (CAST(strftime('%Y', c.signup_date) AS INT) * 12
           + CAST(strftime('%m', c.signup_date) AS INT)) )                  AS months_since_signup
    FROM dim_customer c
    JOIN fact_bookings b
      ON b.customer_id = c.customer_id AND b.status <> 'cancelled'
),
active AS (
    SELECT cohort_month, months_since_signup,
           COUNT(DISTINCT customer_id) AS active_customers
    FROM booking_month
    WHERE months_since_signup BETWEEN 0 AND 6
    GROUP BY cohort_month, months_since_signup
)
SELECT
    a.cohort_month,
    cs.cohort_customers,
    a.months_since_signup,
    a.active_customers,
    ROUND(100.0 * a.active_customers / cs.cohort_customers, 1) AS retention_pct
FROM active a
JOIN cohort_size cs ON cs.cohort_month = a.cohort_month
WHERE a.cohort_month <= '2026-03'            -- only cohorts old enough to have a 6-month window
ORDER BY a.cohort_month, a.months_since_signup;
