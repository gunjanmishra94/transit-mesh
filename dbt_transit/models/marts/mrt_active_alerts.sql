{{ config(materialized='table') }}

-- "Active" = present in the most recent poll. Alerts re-appear on every poll
-- while ongoing (append-only raw table, like trip updates), so this is a
-- dedup down to one row per entity_id, not a fresh event each time.
WITH latest_feed AS (
    SELECT MAX(feed_timestamp) AS ts FROM {{ ref('stg_rt__service_alerts') }}
),
first_seen AS (
    SELECT entity_id, MIN(ingested_at) AS first_seen_at
    FROM {{ ref('stg_rt__service_alerts') }}
    GROUP BY 1
),
deduped_latest AS (
    -- The upstream feed occasionally repeats the exact same entity_id twice
    -- within a single poll (observed: identical content both times, same
    -- feed_timestamp and ingested_at), collapse to one row rather than fail
    -- a uniqueness test on it.
    SELECT
        entity_id,
        ANY_VALUE(cause) AS cause,
        ANY_VALUE(alert_title) AS alert_title,
        ANY_VALUE(description_text) AS description_text,
        ANY_VALUE(stop_ids) AS stop_ids,
        BOOL_OR(is_attribution_notice) AS is_attribution_notice,
        MAX(feed_timestamp) AS feed_timestamp
    FROM {{ ref('stg_rt__service_alerts') }}
    WHERE feed_timestamp = (SELECT ts FROM latest_feed)
    GROUP BY entity_id
)
SELECT
    d.entity_id,
    d.cause,
    d.alert_title,
    d.description_text,
    d.stop_ids,
    fs.first_seen_at,
    d.feed_timestamp AS last_seen_at
FROM deduped_latest d
LEFT JOIN first_seen fs ON d.entity_id = fs.entity_id
WHERE NOT d.is_attribution_notice
