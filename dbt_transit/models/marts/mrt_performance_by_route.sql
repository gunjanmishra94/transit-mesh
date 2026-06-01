{{ config(materialized='table') }}

-- HAVING COUNT(*) >= 20 excludes routes with too few observations for the
-- ranking to mean anything (one bad poll on a rarely-observed route would
-- otherwise look identical to a systematically late one). delay_stddev
-- distinguishes "reliably 5min late" from "swings between -5 and +30" at
-- an equal average. delayed_pct_wilson_lower_bound goes further than the
-- observation floor: a route with 21 observations at 100% delayed isn't
-- actually as certain to be bad as one with 5,000 at 95%, the Wilson
-- lower bound shrinks small samples toward uncertainty instead of taking
-- the raw percentage at face value.
WITH route_stats AS (
    SELECT
        route_id,
        agency_name,
        route_short_name,
        route_long_name,
        route_type_label,
        COUNT(*) AS total_observations,
        SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) AS delayed_count,
        AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
        MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
        STDDEV(arrival_delay_sec) / 60.0 AS delay_stddev_minutes,
        QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
        SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
    FROM {{ ref('int_trip_delays_enriched') }}
    WHERE route_id IS NOT NULL AND route_id != ''
    GROUP BY 1, 2, 3, 4, 5
    HAVING COUNT(*) >= 20
)
SELECT
    *,
    {{ wilson_lower_bound('delayed_count', 'total_observations') }} * 100 AS delayed_pct_wilson_lower_bound
FROM route_stats
