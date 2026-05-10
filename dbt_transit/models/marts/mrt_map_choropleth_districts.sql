{{ config(materialized='table') }}

WITH district_stats AS (
    SELECT
        district_id,
        district_name,
        state_name,
        COUNT(*) AS total_observations,
        AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
        SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
    FROM {{ ref('int_trip_delays_enriched') }}
    WHERE district_id IS NOT NULL
    GROUP BY 1, 2, 3
)
SELECT
    d.*,
    ST_AsGeoJSON(ST_Transform(v.geom, 'EPSG:25832', 'EPSG:4326', true)) AS geojson
FROM district_stats d
JOIN {{ source('transit', 'raw_vg250_districts') }} v ON d.district_id = v.official_key
