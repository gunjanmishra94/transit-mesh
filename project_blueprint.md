# Project Blueprint: German Nationwide Transit Intelligence Platform (GTFS-RT & Static Pipeline)

> **Target Audience for Claude Code Execution:** Production-grade system design specification for an enterprise-grade, local-first spatial-temporal data platform tracking German public transport from country level down to village/stop level using **DuckDB, dbt, Dagster, and Streamlit**.

---

## 1. System Architecture & Tech Stack

```text
 [ GTFS-RT Endpoint: realtime.gtfs.de ] 
 [ Static GTFS Feeds / OSM Boundaries ]
                 │
                 ▼
      [ Dagster Orchestrator ]
         ├── Micro-batch Pollers (Python)
         └── dbt-duckdb Transformations
                 │
                 ▼
       [ DuckDB Analytical Store (.duckdb) ]
                 │
                 ▼
     [ Streamlit Multi-Page App ] (PyDeck 3D / Spatial Analytics)
```

### Technology Matrix
*   **Storage & Query Engine:** **DuckDB** (Columnar, embedded, native spatial extension support, lightning-fast aggregations over millions of events).
*   **Data Modeling & Transformation:** **dbt (with `dbt-duckdb`)** (Modular SQL transformations, incremental models, dimensional modeling, and data tests).
*   **Orchestration:** **Dagster** (Asset-backed orchestration, handling data ingestion schedules, sensor checks, and dbt runs).
*   **Application / Presentation Layer:** **Streamlit** (Multi-page interactive web application powered by **PyDeck** for 3D spatial visualization and **Plotly** for time-series analytics).
*   **Data Sources:** 
    *   *Real-Time:* `https://realtime.gtfs.de/realtime-free.pb` (GTFS-RT Trip Updates & Service Alerts updated every 10s).
    *   *Static Dimensions:* GTFS static feed for Germany (stops, routes, agencies, calendars).
    *   *Spatial Context:* Open administrative boundary polygons for Germany (States / *Bundesländer*, Districts / *Landkreise*, Municipalities / *Gemeinden*).

---

## 2. Data Sourcing Plan (Public, No-Registration Sources Only)

**Constraint:** every source below is anonymously fetchable (direct HTTP GET / ZIP download) with no account signup, API key, or developer-portal registration. Sources that looked open but turned out to be registration-gated on inspection are listed explicitly in §2.7 so they aren't accidentally reached for later.

### 2.1 Source Inventory

| Layer | Source | URL | Format | License | Cadence | Registration |
|---|---|---|---|---|---|---|
| Realtime (national) | gtfs.de realtime mirror | `https://realtime.gtfs.de/realtime-free.pb` | GTFS-RT protobuf (TripUpdates + ServiceAlerts only, no VehiclePositions) | CC BY-SA 4.0 (+ per-agency) | ~every 10–30s | None |
| Static GTFS (national baseline) | gtfs.de / DELFI NeTEx→GTFS conversion | `https://download.gtfs.de/germany/free/latest.zip` | GTFS ZIP (~280MB, ~1.9M trips / ~673K stops) | CC BY-SA 4.0 | Daily | None |
| Static GTFS (regional patch/cross-check) | opendata-oepnv.de feed directory | per-agency ZIPs, HVV, MVV, VRR, VVS, NVV, VBB, NWL, RNV, AVV, VRS | GTFS ZIP | Varies (agency, generally CC BY / DL-DE-BY) | Varies | None (for the static ZIPs) |
| Admin boundaries (Länder → Regierungsbezirke → Kreise → Gemeinden) | BKG VG250 | `https://gdz.bkg.bund.de/.../vg250-01-01.html` | Shapefile / GeoJSON / GML / WFS-WMS | DL-DE-BY-2.0 | ~Annual | None |
| Supplementary geodata (stops, POIs, finer boundary geometry) | Geofabrik OSM extracts | `https://download.geofabrik.de/europe/germany.html` | `.osm.pbf` / Shapefile, per-Bundesland | ODbL 1.0 (attribution + share-alike on derived DBs) | Rolling | None |

### 2.2 Realtime coverage, known gaps and how we handle them

The `realtime-free.pb` feed aggregates 20+ agencies but is explicitly **not** complete: bus coverage is patchy in Rhein-Ruhr and Baden-Württemberg, Hamburg (Stadtwerke Hamburg) has open-license questions pending, and some border regions rely on partial CH/NL feeds. There is no VehiclePositions entity, only TripUpdates + ServiceAlerts.

We do not paper over this. Instead:
- The nationwide static GTFS feed (§2.1, row 2) is the completeness backbone for *structural* coverage (every stop/route/agency in the country exists in the dimension tables even where no RT signal ever arrives).
- A dbt model (`mrt_rt_coverage_by_agency`) computes, per agency/region, the ratio of trips with any RT update in the trailing 24h vs. total scheduled trips from the static feed, surfacing "dark" regions in the Streamlit app rather than silently showing zero delay (which would read as "on time").

### 2.3 Regional feeds, used for patching, not as a live-RT source

Regional Verkehrsverbund **static** GTFS ZIPs are pulled periodically to cross-validate/patch stop metadata (names, accessibility flags, geometry) that may be stale or missing in the national conversion. Their **live** realtime/TRIAS APIs (e.g. VVS, RMV) require email/account registration and are explicitly excluded, only their static downloads are used.

### 2.4 Administrative & spatial reference data

BKG's VG250 dataset provides all administrative levels in a single download, joined to GTFS stops via DuckDB's spatial extension (point-in-polygon on stop lat/lon) to populate `municipality_name`, `district_id`, `state_name` in `stg_gtfs__stops`. Geofabrik OSM extracts are a fallback/supplement when VG250 polygon resolution is too coarse for village-level drill-down, or to validate the spatial join.

### 2.5 Explicitly excluded (require registration despite appearing open)

- **Mobilithek** / NAP.NRW (National Access Point), account signup required.
- **developers.deutschebahn.com** (DB API Marketplace), client-ID registration required for any endpoint.
- **VVS / RMV live TRIAS/RT APIs**, registration or email-contact required (their static GTFS ZIPs are fine and used instead).

### 2.6 New ingestion modules implied by this plan

| Module | Purpose | Schedule |
|---|---|---|
| `ingestion/fetch_rt.py` *(existing)* | Nationwide RT trip updates + alerts | Every 10–60s |
| `ingestion/fetch_static_gtfs.py` *(new)* | Pull + diff nationwide static GTFS into staging (stops/routes/trips/calendar/agency) | Daily |
| `ingestion/fetch_regional_gtfs.py` *(new, optional)* | Pull regional Verkehrsverbund static feeds to patch/cross-check | Weekly |
| `ingestion/fetch_admin_boundaries.py` *(new)* | Pull BKG VG250 (+ optional Geofabrik OSM boundaries) into a spatial reference table | Annual / manual trigger |

Corresponding Dagster assets (`static_gtfs_asset`, `admin_boundaries_asset`) are added alongside the existing `raw_gtfs_rt_asset`, each on its own schedule rather than the current single every-minute job.

### 2.7 Reference data flagged for manual verification before use

destatis.de / Zensus municipality population data and the DB InfraGO open-data portal were not independently confirmed as registration-free during this pass, treat as optional enrichment and verify access terms before wiring them into the pipeline.

---

## 3. Directory Structure

```text
german-transit-analytics/
├── .env
├── README.md
├── pyproject.toml
├── duckdb_data/
│   └── transit.duckdb
├── ingestion/
│   ├── __init__.py
│   ├── fetch_rt.py
│   └── parse_protobuf.py
├── dbt_transit/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_gtfs__stops.sql
│   │   │   ├── stg_gtfs__routes.sql
│   │   │   └── stg_rt__trip_updates.sql
│   │   ├── intermediate/
│   │   │   └── int_trip_delays_enriched.sql
│   │   └── marts/
│   │   │   ├── mrt_performance_by_stop.sql
│   │   │   ├── mrt_performance_by_municipality.sql
│   │   │   └── mrt_performance_national.sql
└── orchestrator/
    ├── __init__.py
    └── definitions.py
```

---

## 4. Implementation Files & Code Specifications

### 4.1. Python Ingestion (`ingestion/fetch_rt.py`)
Polls the German GTFS-RT protobuf endpoint, parses trip updates, and appends raw telemetry directly to DuckDB.

```python
import os
import duckdb
import requests
from google.transit import gtfs_realtime_pb2
from datetime import datetime

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")
RT_URL = "https://realtime.gtfs.de/realtime-free.pb"

def ingest_gtfs_rt():
    response = requests.get(RT_URL, timeout=30)
    response.raise_for_status()
    
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    
    records = []
    ingested_at = datetime.utcnow()
    
    for entity in feed.entity:
        if entity.HasField("trip_update"):
            tu = entity.trip_update
            trip_id = tu.trip.trip_id
            route_id = tu.trip.route_id
            
            for su in tu.stop_time_update:
                stop_id = su.stop_id
                arrival_delay = su.arrival.delay if su.HasField("arrival") else 0
                departure_delay = su.departure.delay if su.HasField("departure") else 0
                
                records.append({
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "stop_id": stop_id,
                    "arrival_delay_sec": arrival_delay,
                    "departure_delay_sec": departure_delay,
                    "ingested_at": ingested_at
                })
                
    if not records:
        return 0

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_trip_updates (
            trip_id VARCHAR,
            route_id VARCHAR,
            stop_id VARCHAR,
            arrival_delay_sec INTEGER,
            departure_delay_sec INTEGER,
            ingested_at TIMESTAMP
        )
    """)
    
    conn.register("df_records", records)
    conn.execute("INSERT INTO raw_trip_updates SELECT * FROM df_records")
    conn.close()
    
    return len(records)

if __name__ == "__main__":
    count = ingest_gtfs_rt()
    print(f"Successfully ingested {count} real-time trip update events.")
```

---

### 4.2. dbt Models (`dbt_transit/models/`)

#### Staging: `models/staging/stg_rt__trip_updates.sql`
```sql
{{ config(materialized='view') }}

SELECT
    trip_id,
    route_id,
    stop_id,
    arrival_delay_sec,
    departure_delay_sec,
    ingested_at,
    CAST(ingested_at AS DATE) as ingestion_date
FROM {{ source('transit', 'raw_trip_updates') }}
```

#### Intermediate: `models/intermediate/int_trip_delays_enriched.sql`
Joins real-time updates with static stop hierarchies (mapping stops to villages/municipalities via spatial or relational keys).

```sql
{{ config(materialized='incremental', unique_key=['trip_id', 'stop_id', 'ingested_at']) }}

SELECT
    t.trip_id,
    t.route_id,
    t.stop_id,
    s.stop_name,
    s.municipality_name,
    s.district_id,
    s.state_name,
    t.arrival_delay_sec,
    t.departure_delay_sec,
    t.ingested_at,
    CASE 
        WHEN t.arrival_delay_sec > 300 THEN TRUE 
        ELSE FALSE 
    END AS is_delayed
FROM {{ ref('stg_rt__trip_updates') }} t
LEFT JOIN {{ ref('stg_gtfs__stops') }} s ON t.stop_id = s.stop_id

{% if is_incremental() %}
  WHERE t.ingested_at > (SELECT MAX(ingested_at) FROM {{ this }})
{% endif %}
```

#### Mart: `models/marts/mrt_performance_by_municipality.sql`
Rolls up delay telemetry to the village/municipality level for hyper-local drill-downs.

```sql
{{ config(materialized='table') }}

SELECT
    state_name,
    district_id,
    municipality_name,
    COUNT(*) as total_observations,
    AVG(arrival_delay_sec) / 60.0 as avg_delay_minutes,
    SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as delayed_percentage,
    MAX(ingested_at) as last_updated
FROM {{ ref('int_trip_delays_enriched') }}
GROUP BY 1, 2, 3
```

---

### 4.3. Dagster Orchestrator (`orchestrator/definitions.py`)
Coordinates micro-batch ingestion and execution schedules.

```python
from dagster import asset, Definitions, define_asset_job, ScheduleDefinition
from ingestion.fetch_rt import ingest_gtfs_rt

@asset(group_name="ingestion")
def raw_gtfs_rt_asset():
    """Polls gtfs.de real-time protobuf feed and loads into DuckDB."""
    count = ingest_gtfs_rt()
    return f"Ingested {count} records."

transit_job = define_asset_job("transit_pipeline_job", selection="*")
transit_schedule = ScheduleDefinition(
    job=transit_job,
    cron_schedule="* * * * *", # Every minute micro-batching
)

defs = Definitions(
    assets=[raw_gtfs_rt_asset],
    schedules=[transit_schedule]
)
```

---

### 4.4. Streamlit Multi-Page Dashboard (`app/main.py`)
Interactive spatial-temporal interface with country-to-village drill-downs.

```python
import streamlit as st
import duckdb

st.set_page_config(page_title="German Transit Intelligence", layout="wide")

DB_PATH = "duckdb_data/transit.duckdb"

@st.cache_resource
def get_db_connection():
    return duckdb.connect(DB_PATH, read_only=True)

try:
    conn = get_db_connection()
except Exception:
    st.error("DuckDB file not found or not initialized yet. Run ingestion first.")
    st.stop()

st.title("🇩🇪 Deutsche Transit Intelligence Platform")
st.markdown("Real-time telemetry, delay propagation, and spatial analytics from country to village level.")

# Sidebar Filters for Hierarchy Drill-Down
st.sidebar.header("Spatial Drill-Down")
states = [row[0] for row in conn.execute("SELECT DISTINCT state_name FROM mrt_performance_by_municipality WHERE state_name IS NOT NULL").fetchall()]
selected_state = st.sidebar.selectbox("Select Federal State (Bundesland)", ["All Germany"] + states)

if selected_state == "All Germany":
    df_map = conn.execute("""
        SELECT state_name, AVG(avg_delay_minutes) as avg_delay, SUM(total_observations) as obs
        FROM mrt_performance_by_municipality GROUP BY state_name
    """).df()
    st.subheader("Country-Level Macro View: Average Delays by State")
    st.dataframe(df_map, use_container_width=True)
else:
    districts = [row[0] for row in conn.execute("SELECT DISTINCT district_id FROM mrt_performance_by_municipality WHERE state_name = ?", [selected_state]).fetchall()]
    selected_district = st.sidebar.selectbox("Select District (Landkreis)", ["All Districts"] + districts)
    
    if selected_district == "All Districts":
        df_micro = conn.execute("""
            SELECT municipality_name, avg_delay_minutes, delayed_percentage, total_observations
            FROM mrt_performance_by_municipality WHERE state_name = ?
        """, [selected_state]).df()
        st.subheader(f"District-Level View: {selected_state}")
        st.bar_chart(df_micro.set_index("municipality_name")["avg_delay_minutes"])
    else:
        df_village = conn.execute("""
            SELECT municipality_name, avg_delay_minutes, delayed_percentage 
            FROM mrt_performance_by_municipality WHERE district_id = ?
        """, [selected_district]).df()
        st.subheader(f"Village / Municipality Micro-View: {selected_district}")
        st.dataframe(df_village, use_container_width=True)
```

---

## 5. Execution Prompt for Claude
Paste this blueprint into Claude with the prompt:
> *"Please act as my senior engineering pair programmer. Using the architectural blueprint above, help me initialize this repository, write out the remaining setup configuration files (`pyproject.toml`, `dbt_project.yml`, `profiles.yml`), and run the first local ingestion test."*