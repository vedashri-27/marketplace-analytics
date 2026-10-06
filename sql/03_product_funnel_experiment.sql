-- Product analytics: the conversion funnel and the checkout_v2 A/B test.


-- Q1 | Conversion funnel with step and absolute drop-off
-- Business question: Where in the journey (view -> cart -> checkout -> book) do
--   we lose the most people, and what is the single biggest leak to fix?
-- Technique: one pass to count each stage, UNION ALL into a tidy stage table,
--   then LAG() windows for step-conversion and drop-off vs the previous step.
WITH funnel AS (
    SELECT
        COUNT(*)                   AS sessions,
        SUM(stage_view)            AS viewed,
        SUM(stage_cart)            AS added_to_cart,
        SUM(stage_checkout)        AS checkout_started,
        SUM(converted)             AS booked
    FROM fact_sessions
),
stages AS (
    SELECT 1 AS step_no, 'Session'          AS stage, sessions         AS users FROM funnel
    UNION ALL SELECT 2, 'Viewed experience', viewed           FROM funnel
    UNION ALL SELECT 3, 'Added to cart',     added_to_cart    FROM funnel
    UNION ALL SELECT 4, 'Checkout started',  checkout_started FROM funnel
    UNION ALL SELECT 5, 'Booked',            booked           FROM funnel
)
SELECT
    stage,
    users,
    ROUND(100.0 * users / FIRST_VALUE(users) OVER (ORDER BY step_no), 1) AS pct_of_sessions,
    ROUND(100.0 * users / LAG(users) OVER (ORDER BY step_no), 1)         AS step_conversion_pct,
    LAG(users) OVER (ORDER BY step_no) - users                           AS users_lost_vs_prev
FROM stages
ORDER BY step_no;


-- Q2 | Funnel by device — where mobile under-performs
-- Business question: Is our conversion problem device-specific (e.g. a clunky
--   mobile checkout)?
-- Technique: conditional aggregation pivoted by stage, grouped by device.
SELECT
    device,
    COUNT(*)                                                   AS sessions,
    ROUND(100.0 * SUM(stage_cart)     / COUNT(*), 1)           AS view_to_cart_equiv_pct,
    ROUND(100.0 * SUM(stage_checkout) / NULLIF(SUM(stage_cart), 0), 1)       AS cart_to_checkout_pct,
    ROUND(100.0 * SUM(converted)      / NULLIF(SUM(stage_checkout), 0), 1)   AS checkout_to_book_pct,
    ROUND(100.0 * SUM(converted)      / COUNT(*), 2)           AS overall_conversion_pct
FROM fact_sessions
GROUP BY device
ORDER BY sessions DESC;


-- Q3 | A/B experiment readout — "checkout_v2"
-- Business question: Did the new checkout (treatment) actually lift conversion
--   vs control, and by how much?
-- Technique: filter to post-launch randomised traffic, aggregate per arm, then a
--   cross join to the control arm to compute absolute and relative lift. (Formal
--   statistical significance / p-value is computed in python/03_analysis.py — SQL
--   reports the point estimates and sample sizes that feed it.)
WITH arm AS (
    SELECT
        experiment_group                                        AS variant,
        COUNT(*)                                                AS sessions,
        SUM(converted)                                          AS bookings,
        1.0 * SUM(converted) / COUNT(*)                         AS conv_rate
    FROM fact_sessions
    WHERE experiment_group IN ('control', 'treatment')          -- randomised traffic only
    GROUP BY experiment_group
),
ctrl AS (SELECT conv_rate AS control_rate FROM arm WHERE variant = 'control')
SELECT
    a.variant,
    a.sessions,
    a.bookings,
    ROUND(100.0 * a.conv_rate, 2)                               AS conversion_pct,
    ROUND(100.0 * (a.conv_rate - c.control_rate), 2)            AS abs_lift_pp,
    ROUND(100.0 * (a.conv_rate - c.control_rate)
          / NULLIF(c.control_rate, 0), 1)                       AS rel_lift_pct
FROM arm a CROSS JOIN ctrl c
ORDER BY a.variant;
