{{ config(materialized='incremental', unique_key=['trip_id', 'stop_id', 'ingested_at']) }}

SELECT
    t.trip_id,
    trips.route_id,
    routes.agency_id,
    t.stop_id,
    s.stop_name,
    s.municipality_name,
    s.district_id,
    s.district_name,
    s.state_name,
    t.arrival_delay_sec,
    t.departure_delay_sec,
    t.feed_timestamp,
    t.ingested_at,
    CASE
        WHEN t.arrival_delay_sec > 300 THEN TRUE
        ELSE FALSE
    END AS is_delayed
FROM {{ ref('stg_rt__trip_updates') }} t
LEFT JOIN {{ ref('stg_gtfs__trips') }} trips ON t.trip_id = trips.trip_id
LEFT JOIN {{ ref('stg_gtfs__routes') }} routes ON trips.route_id = routes.route_id
LEFT JOIN {{ ref('stg_gtfs__stops') }} s ON t.stop_id = s.stop_id

{% if is_incremental() %}
  WHERE t.ingested_at > (SELECT MAX(ingested_at) FROM {{ this }})
{% endif %}
