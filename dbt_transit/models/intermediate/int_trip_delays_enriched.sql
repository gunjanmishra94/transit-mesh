{{ config(materialized='incremental', unique_key=['trip_id', 'stop_id', 'ingested_at']) }}

SELECT
    t.trip_id,
    trips.route_id,
    routes.agency_id,
    agency.agency_name,
    routes.route_short_name,
    routes.route_long_name,
    routes.route_type,
    {{ route_type_label('routes.route_type') }} AS route_type_label,
    t.stop_id,
    s.stop_name,
    s.stop_lat,
    s.stop_lon,
    s.municipality_id,
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
LEFT JOIN {{ ref('stg_gtfs__agency') }} agency ON routes.agency_id = agency.agency_id
LEFT JOIN {{ ref('stg_gtfs__stops') }} s ON t.stop_id = s.stop_id

-- Excludes a day-boundary/midnight-rollover bug found on Verkehrsverbund
-- Rhein-Sieg route 10930: 141 observations at exactly -1440.0min and 141 at
-- -1439.5min (i.e. -24h, almost to the second) — the unmistakable signature
-- of a date mismatch, not a real delay. No real-world transit delay is
-- legitimately within a minute of a full day; 12h is a generous cutoff that
-- clears this artifact while still passing genuinely severe real disruptions.
WHERE (t.arrival_delay_sec IS NULL OR ABS(t.arrival_delay_sec) <= 43200)
  AND (t.departure_delay_sec IS NULL OR ABS(t.departure_delay_sec) <= 43200)

{% if is_incremental() %}
  AND t.ingested_at > (SELECT MAX(ingested_at) FROM {{ this }})
{% endif %}
