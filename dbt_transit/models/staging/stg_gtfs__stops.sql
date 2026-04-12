{{ config(materialized='view') }}

-- Sourced from stg_gtfs_stops_enriched, which ingestion/enrich_stops_with_boundaries.py
-- builds via a point-in-polygon spatial join against VG250 (see project_blueprint.md §2.4).
SELECT
    stop_id,
    stop_name,
    parent_station,
    location_type,
    platform_code,
    stop_lat,
    stop_lon,
    municipality_id,
    municipality_name,
    district_id,
    district_name,
    state_code,
    state_name
FROM {{ source('transit', 'stg_gtfs_stops_enriched') }}
