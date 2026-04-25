{{ config(materialized='table') }}

-- HAVING COUNT(*) >= 20 excludes routes with too few observations for the
-- ranking to mean anything (one bad poll on a rarely-observed route would
-- otherwise look identical to a systematically late one).
SELECT
    route_id,
    agency_name,
    route_short_name,
    route_long_name,
    route_type_label,
    COUNT(*) AS total_observations,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
    QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
FROM {{ ref('int_trip_delays_enriched') }}
WHERE route_id IS NOT NULL AND route_id != ''
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 20
