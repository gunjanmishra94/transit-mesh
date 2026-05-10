{{ config(materialized='table') }}

-- avg_delay_minutes alone can mislead for high-volume regions: it's easily
-- pulled toward zero by a large majority of on-time trips even when a
-- meaningful tail is badly delayed. median/p90 alongside delayed_percentage
-- give the actual shape instead of one misleading point estimate.
SELECT
    state_name,
    COUNT(*) AS total_observations,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
    STDDEV(arrival_delay_sec) / 60.0 AS delay_stddev_minutes,
    QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
    MAX(ingested_at) AS last_updated
FROM {{ ref('int_trip_delays_enriched') }}
GROUP BY 1
