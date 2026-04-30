{{ config(materialized='view') }}

-- effect is always 'UNKNOWN_EFFECT' in this feed (zero variance) and
-- route_ids/agency_ids are never populated (0 of 1.5M rows as observed) —
-- there is no way to link an alert to a specific route or agency here.
-- header_text is only populated ~8% of the time; description_text always is.
--
-- ~77% of all distinct entities are a legal attribution notice ("Echtzeitdaten
-- aufbereitet von GTFS.de, bereitgestellt von <source>"), not a real service
-- alert — this feed (mis)uses the GTFS-RT Alerts mechanism for that plus
-- static vehicle-accessibility tags (Niederflur, Rollstuhlgeeignet, ...), not
-- just genuine disruptions. is_attribution_notice isolates the unambiguous,
-- high-volume noise so downstream models don't present it as a disruption.
SELECT
    entity_id,
    cause,
    effect,
    header_text,
    description_text,
    COALESCE(header_text, description_text) AS alert_title,
    description_text LIKE 'Echtzeitdaten aufbereitet%' AS is_attribution_notice,
    route_ids,
    stop_ids,
    agency_ids,
    feed_timestamp,
    ingested_at
FROM {{ source('transit', 'raw_service_alerts') }}
