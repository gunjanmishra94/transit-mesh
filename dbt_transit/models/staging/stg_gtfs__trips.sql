{{ config(materialized='view') }}

SELECT
    trip_id,
    route_id,
    service_id
FROM {{ source('transit', 'raw_gtfs_trips') }}
