-- Dynamic pricing: realised uplift, the last-minute premium, demand vs utilisation.


-- Q1 | Realised uplift from dynamic pricing, by category
-- Business question: How much incremental GMV is dynamic pricing actually
--   capturing over flat base prices, and where does it work best?
-- Technique: compare effective vs base price at booking grain, aggregate the
--   delta into incremental GMV, express as an uplift %. JOIN to the experience
--   dimension for category context.
WITH priced AS (
    SELECT
        e.category,
        b.num_guests,
        b.base_price_usd,
        b.effective_price_usd,
        (b.effective_price_usd - b.base_price_usd) * b.num_guests AS uplift_usd,
        b.base_price_usd * b.num_guests                          AS base_gmv_usd,
        b.gbv_usd
    FROM fact_bookings b
    JOIN dim_experience e ON e.experience_id = b.experience_id
    WHERE b.status <> 'cancelled'
)
SELECT
    category,
    COUNT(*)                                             AS bookings,
    ROUND(SUM(base_gmv_usd), 0)                          AS base_gmv_usd,
    ROUND(SUM(uplift_usd), 0)                            AS pricing_uplift_usd,
    ROUND(100.0 * SUM(uplift_usd)
          / NULLIF(SUM(base_gmv_usd), 0), 1)            AS uplift_pct,
    ROUND(AVG(effective_price_usd / NULLIF(base_price_usd, 0)), 3) AS avg_price_multiplier
FROM priced
GROUP BY category
ORDER BY pricing_uplift_usd DESC;


-- Q2 | Lead-time pricing & booking behaviour
-- Business question: Does the last-minute premium hold up, and how do volume and
--   AOV shift as travel date approaches?
-- Technique: CASE bucketing of a continuous variable (lead days), aggregate
--   price multiplier / AOV / volume per bucket, ordered for a clean curve.
SELECT
    CASE
        WHEN lead_days <= 2  THEN '0-2 d (last minute)'
        WHEN lead_days <= 7  THEN '3-7 d'
        WHEN lead_days <= 30 THEN '8-30 d'
        WHEN lead_days <= 60 THEN '31-60 d'
        ELSE '60+ d'
    END                                                 AS lead_time_bucket,
    CASE
        WHEN lead_days <= 2  THEN 1 WHEN lead_days <= 7  THEN 2
        WHEN lead_days <= 30 THEN 3 WHEN lead_days <= 60 THEN 4 ELSE 5
    END                                                 AS bucket_order,
    COUNT(*)                                            AS bookings,
    ROUND(AVG(price_multiplier), 3)                     AS avg_price_multiplier,
    ROUND(AVG(gbv_usd), 1)                              AS avg_booking_value_usd,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS pct_of_bookings
FROM fact_bookings
WHERE status <> 'cancelled'
GROUP BY lead_time_bucket, bucket_order
ORDER BY bucket_order;


-- Q3 | Demand vs utilisation from the daily pricing/inventory snapshot
-- Business question: When demand runs hot, are we selling out (leaving money on
--   the table) or do we have slack to absorb more marketing push?
-- Technique: bucket the demand index, compute utilisation = booked / available
--   from the supply-side snapshot, show how fill-rate rises with demand.
SELECT
    CASE
        WHEN demand_index < 0.9  THEN 'Low (<0.9)'
        WHEN demand_index < 1.1  THEN 'Normal (0.9-1.1)'
        WHEN demand_index < 1.3  THEN 'High (1.1-1.3)'
        ELSE 'Peak (1.3+)'
    END                                                       AS demand_band,
    CASE
        WHEN demand_index < 0.9 THEN 1 WHEN demand_index < 1.1 THEN 2
        WHEN demand_index < 1.3 THEN 3 ELSE 4
    END                                                       AS band_order,
    COUNT(*)                                                  AS exp_days,
    ROUND(AVG(dynamic_price_usd / NULLIF(base_price_usd, 0)), 3) AS avg_price_multiplier,
    ROUND(100.0 * SUM(slots_booked) / SUM(slots_available), 1)   AS utilisation_pct
FROM fact_daily_pricing
GROUP BY demand_band, band_order
ORDER BY band_order;
