{{ config(materialized='table') }}

-- Distinct question from mrt_rt_coverage_by_agency: coverage asks "does this
-- agency report realtime data at all", this asks "how reliable is that
-- agency's service" — only agencies with actual RT observations appear here,
-- which is correct (there's nothing to score for a dark agency).
SELECT
    agency_id,
    agency_name,
    COUNT(*) AS total_observations,
    COUNT(DISTINCT route_id) AS distinct_routes,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
    STDDEV(arrival_delay_sec) / 60.0 AS delay_stddev_minutes,
    QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
FROM {{ ref('int_trip_delays_enriched') }}
WHERE agency_id IS NOT NULL
GROUP BY 1, 2
HAVING COUNT(*) >= 20
