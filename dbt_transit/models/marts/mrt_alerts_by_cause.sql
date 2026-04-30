{{ config(materialized='table') }}

-- Attribution notices excluded — see stg_rt__service_alerts for why they'd
-- otherwise dominate this breakdown (~77% of all distinct alert entities).
WITH latest_feed AS (
    SELECT MAX(feed_timestamp) AS ts FROM {{ ref('stg_rt__service_alerts') }}
)
SELECT
    cause,
    COUNT(DISTINCT entity_id) AS total_ever_seen,
    COUNT(DISTINCT CASE WHEN feed_timestamp = (SELECT ts FROM latest_feed) THEN entity_id END) AS currently_active
FROM {{ ref('stg_rt__service_alerts') }}
WHERE NOT is_attribution_notice
GROUP BY 1
ORDER BY total_ever_seen DESC
