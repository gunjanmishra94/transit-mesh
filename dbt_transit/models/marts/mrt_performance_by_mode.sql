{{ config(materialized='table') }}

-- National only: median/p90 don't combine validly across a state-level
-- pre-aggregation, so a per-state mode breakdown is computed live in the
-- app (see app/main.py) instead of materialized here.
SELECT
    route_type_label,
    COUNT(*) AS total_observations,
    COUNT(DISTINCT route_id) AS distinct_routes,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
    STDDEV(arrival_delay_sec) / 60.0 AS delay_stddev_minutes,
    QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
    MAX(ingested_at) AS last_updated
FROM {{ ref('int_trip_delays_enriched') }}
WHERE route_type_label IS NOT NULL
GROUP BY 1
