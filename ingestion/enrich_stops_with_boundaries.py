import os

from ingestion.duckdb_utils import connect_with_retry

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")

# VG250 municipality AGS codes are hierarchical: the first 5 digits of a
# municipality's 8-digit AGS *are* its district's AGS, and the first 2
# digits of that are the state code — so district/state can be derived
# from the municipality match without two more spatial joins.
ENRICH_STOPS_SQL = """
CREATE OR REPLACE TABLE stg_gtfs_stops_enriched AS
WITH stops_projected AS (
    SELECT
        stop_id,
        stop_name,
        parent_station,
        location_type,
        platform_code,
        CAST(stop_lat AS DOUBLE) AS stop_lat,
        CAST(stop_lon AS DOUBLE) AS stop_lon,
        ST_Transform(
            ST_Point(CAST(stop_lon AS DOUBLE), CAST(stop_lat AS DOUBLE)),
            'EPSG:4326', 'EPSG:25832', true
        ) AS geom_utm32s
    FROM raw_gtfs_stops
    WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
)
SELECT
    s.stop_id,
    s.stop_name,
    s.parent_station,
    s.location_type,
    s.platform_code,
    s.stop_lat,
    s.stop_lon,
    gem.official_key AS municipality_id,
    gem.name AS municipality_name,
    LEFT(gem.official_key, 5) AS district_id,
    krs.name AS district_name,
    gem.state_code,
    lan.name AS state_name
FROM stops_projected s
LEFT JOIN raw_vg250_municipalities gem ON ST_Contains(gem.geom, s.geom_utm32s)
LEFT JOIN raw_vg250_districts krs ON krs.official_key = LEFT(gem.official_key, 5)
LEFT JOIN raw_vg250_states lan ON lan.official_key = gem.state_code
"""

REQUIRED_TABLES = [
    "raw_gtfs_stops",
    "raw_vg250_municipalities",
    "raw_vg250_districts",
    "raw_vg250_states",
]


def enrich_stops():
    conn = connect_with_retry(DB_PATH)
    conn.execute("INSTALL spatial; LOAD spatial;")

    existing = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        conn.close()
        raise RuntimeError(
            f"Missing required tables {missing}. "
            "Run fetch_static_gtfs.py and fetch_admin_boundaries.py first."
        )

    conn.execute(ENRICH_STOPS_SQL)
    total, matched = conn.execute("""
        SELECT COUNT(*), COUNT(municipality_name) FROM stg_gtfs_stops_enriched
    """).fetchone()
    conn.close()
    return total, matched


if __name__ == "__main__":
    total, matched = enrich_stops()
    print(f"stg_gtfs_stops_enriched: {total} rows, {matched} matched to a municipality "
          f"({matched / total:.1%}), {total - matched} unmatched (likely cross-border stops)")
