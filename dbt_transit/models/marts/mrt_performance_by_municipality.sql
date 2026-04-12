{{ config(materialized='table') }}

SELECT
    state_name,
    district_id,
    district_name,
    municipality_name,
    COUNT(*) AS total_observations,
    AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
    MAX(ingested_at) AS last_updated
FROM {{ ref('int_trip_delays_enriched') }}
GROUP BY 1, 2, 3, 4
