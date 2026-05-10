{{ config(materialized='table') }}

-- Pre-computed GeoJSON (reprojected UTM32s -> WGS84) so the app renders a
-- real filled-polygon map instead of a point scatter, without doing the
-- geometry transform on every page load.
SELECT
    n.state_name,
    n.total_observations,
    n.avg_delay_minutes,
    n.delayed_percentage,
    ST_AsGeoJSON(ST_Transform(s.geom, 'EPSG:25832', 'EPSG:4326', true)) AS geojson
FROM {{ ref('mrt_performance_national') }} n
JOIN {{ source('transit', 'raw_vg250_states') }} s ON n.state_name = s.name
