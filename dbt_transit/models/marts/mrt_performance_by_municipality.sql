{{ config(materialized='table') }}

WITH stop_locations AS (
    SELECT DISTINCT stop_id, municipality_id, stop_lat, stop_lon
    FROM {{ ref('int_trip_delays_enriched') }}
),
municipality_centroids AS (
    -- Centroid of the municipality's distinct stops, not observation-weighted
    -- (a heavily-polled stop shouldn't pull the map marker toward it).
    SELECT municipality_id, AVG(stop_lat) AS centroid_lat, AVG(stop_lon) AS centroid_lon
    FROM stop_locations
    GROUP BY 1
)
SELECT
    m.state_name,
    m.district_id,
    m.district_name,
    m.municipality_id,
    m.municipality_name,
    c.centroid_lat,
    c.centroid_lon,
    COUNT(*) AS total_observations,
    AVG(m.arrival_delay_sec) / 60.0 AS avg_delay_minutes,
    SUM(CASE WHEN m.is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
    MAX(m.ingested_at) AS last_updated
FROM {{ ref('int_trip_delays_enriched') }} m
LEFT JOIN municipality_centroids c ON m.municipality_id = c.municipality_id
GROUP BY 1, 2, 3, 4, 5, 6, 7
