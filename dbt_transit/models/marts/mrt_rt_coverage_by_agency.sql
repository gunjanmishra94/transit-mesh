{{ config(materialized='table') }}

-- Surfaces agencies/regions with no realtime signal (blueprint §2.2) rather
-- than letting them silently read as "0 delay" in the app.
WITH scheduled_trips AS (
    SELECT
        routes.agency_id,
        COUNT(DISTINCT trips.trip_id) AS scheduled_trip_count
    FROM {{ ref('stg_gtfs__trips') }} trips
    LEFT JOIN {{ ref('stg_gtfs__routes') }} routes ON trips.route_id = routes.route_id
    GROUP BY 1
),
observed_trips AS (
    SELECT
        routes.agency_id,
        COUNT(DISTINCT rt.trip_id) AS observed_trip_count
    FROM {{ ref('stg_rt__trip_updates') }} rt
    LEFT JOIN {{ ref('stg_gtfs__trips') }} trips ON rt.trip_id = trips.trip_id
    LEFT JOIN {{ ref('stg_gtfs__routes') }} routes ON trips.route_id = routes.route_id
    WHERE rt.ingested_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
    GROUP BY 1
)
SELECT
    a.agency_id,
    a.agency_name,
    COALESCE(s.scheduled_trip_count, 0) AS scheduled_trip_count,
    COALESCE(o.observed_trip_count, 0) AS observed_trip_count,
    CASE
        WHEN COALESCE(s.scheduled_trip_count, 0) = 0 THEN NULL
        ELSE COALESCE(o.observed_trip_count, 0) * 100.0 / s.scheduled_trip_count
    END AS rt_coverage_pct
FROM {{ ref('stg_gtfs__agency') }} a
LEFT JOIN scheduled_trips s ON a.agency_id = s.agency_id
LEFT JOIN observed_trips o ON a.agency_id = o.agency_id
ORDER BY rt_coverage_pct NULLS LAST
