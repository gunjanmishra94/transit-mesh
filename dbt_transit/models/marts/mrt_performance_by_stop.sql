{{ config(materialized='table') }}

SELECT
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    municipality_id,
    municipality_name,
    district_name,
    state_name,
    COUNT(*) AS total_observations,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
    MAX(ingested_at) AS last_updated
FROM {{ ref('int_trip_delays_enriched') }}
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
