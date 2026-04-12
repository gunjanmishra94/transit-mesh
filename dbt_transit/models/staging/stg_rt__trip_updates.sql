{{ config(materialized='view') }}

-- route_id is dropped here: this feed leaves TripDescriptor.route_id empty on
-- every entity (see ingestion/fetch_rt.py), so route/agency is resolved via a
-- trip_id join against stg_gtfs__trips in int_trip_delays_enriched instead.
SELECT
    entity_id,
    trip_id,
    stop_id,
    arrival_delay_sec,
    departure_delay_sec,
    feed_timestamp,
    ingested_at,
    CAST(ingested_at AS DATE) AS ingestion_date
FROM {{ source('transit', 'raw_trip_updates') }}
