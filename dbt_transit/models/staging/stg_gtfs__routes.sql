{{ config(materialized='view') }}

SELECT
    route_id,
    agency_id,
    route_short_name,
    route_long_name,
    CAST(route_type AS INTEGER) AS route_type,
    route_color,
    route_text_color
FROM {{ source('transit', 'raw_gtfs_routes') }}
