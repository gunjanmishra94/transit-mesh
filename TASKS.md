# Build Tasks: German Nationwide Transit Intelligence Platform

Staged implementation plan derived from `project_blueprint.md`. Work top to bottom — each phase produces something runnable before the next begins.

---

## Phase 0 — Repo Scaffolding

- [ ] Init project structure per blueprint §3 (Directory Structure): `ingestion/`, `dbt_transit/`, `orchestrator/`, `app/`, `duckdb_data/`
- [ ] `pyproject.toml` with deps: `duckdb`, `dbt-duckdb`, `dagster`, `dagster-webserver`, `streamlit`, `pydeck`, `plotly`, `requests`, `gtfs-realtime-bindings`
- [ ] `.env` + `.env.example` (DB path, any config — no API keys needed per §2 sourcing constraint)
- [ ] `README.md` with setup/run instructions
- [ ] `.gitignore` (`duckdb_data/`, `.env`, `dbt_transit/target/`, `dbt_transit/logs/`)
- [ ] Initialize git repo, first commit

## Phase 1 — Static Nationwide Baseline (do this before realtime)

Static GTFS is the structural backbone for "every place in Germany" — build this first so downstream models have a complete stop/route/agency universe even before realtime data flows.

- [ ] `ingestion/fetch_static_gtfs.py` — download `https://download.gtfs.de/germany/free/latest.zip`, unzip, bulk-load `stops.txt`, `routes.txt`, `trips.txt`, `calendar.txt`, `agency.txt` into DuckDB raw tables
- [ ] `ingestion/fetch_admin_boundaries.py` — download BKG VG250 (Länder/Kreise/Gemeinden), load into a spatial reference table via DuckDB `spatial` extension
- [ ] Point-in-polygon join: enrich `raw_stops` with `municipality_name` / `district_id` / `state_name` from VG250
- [ ] Sanity check: row counts per Bundesland, confirm no state has zero stops
- [ ] (Optional, later) `ingestion/fetch_regional_gtfs.py` for VVS/HVV/MVV/etc. static feeds to patch gaps — defer until Phase 1 baseline is validated

## Phase 2 — Realtime Ingestion

- [ ] `ingestion/fetch_rt.py` per blueprint §4.1 — poll `realtime-free.pb`, parse TripUpdates, write to `raw_trip_updates`
- [ ] Extend parser for ServiceAlerts entities (feed includes them; blueprint's current code only handles trip_update)
- [ ] Manual test run: confirm non-zero records ingested, spot-check against known routes (e.g. a Berlin or Munich line)
- [ ] Add a `source_agency` / `feed_coverage_flag` column so downstream models can distinguish "no delay" from "no data"

## Phase 3 — dbt Modeling

- [ ] `dbt_transit/dbt_project.yml`, `profiles.yml` (duckdb adapter, path to `duckdb_data/transit.duckdb`)
- [ ] Staging: `stg_gtfs__stops`, `stg_gtfs__routes`, `stg_gtfs__agency`, `stg_rt__trip_updates` (blueprint §4.2)
- [ ] Intermediate: `int_trip_delays_enriched` (join RT to enriched static stops)
- [ ] Marts: `mrt_performance_by_stop`, `mrt_performance_by_municipality`, `mrt_performance_national`
- [ ] New mart: `mrt_rt_coverage_by_agency` (blueprint §2.2) — trips-with-RT ÷ scheduled-trips per agency/region, trailing 24h
- [ ] dbt tests: not-null / relationships on keys, accepted-range on delay minutes
- [ ] `dbt run` + `dbt test` clean pass

## Phase 4 — Orchestration (Dagster)

- [ ] `orchestrator/definitions.py`: `raw_gtfs_rt_asset` (existing, every-minute schedule)
- [ ] Add `static_gtfs_asset` (daily schedule)
- [ ] Add `admin_boundaries_asset` (annual/manual trigger — VG250 updates infrequently)
- [ ] Wire dbt run as a downstream asset dependency (dagster-dbt) after each ingestion asset completes
- [ ] Verify Dagster UI shows correct asset graph and schedules fire independently

## Phase 5 — Streamlit App

- [ ] `app/main.py` per blueprint §4.4 — state → district → municipality drill-down
- [ ] Add coverage indicator (from `mrt_rt_coverage_by_agency`) so dark/no-data regions are visibly flagged, not shown as "0 delay"
- [ ] PyDeck map layer for spatial view (blueprint mentions PyDeck 3D — not yet in the sample code, needs building)
- [ ] Plotly time-series panel for delay trends
- [ ] Manual smoke test: load app, click through all three drill-down levels, confirm no crashes on states with sparse data

## Phase 6 — Data Quality & Gap Documentation

- [ ] Document known coverage gaps (Rhein-Ruhr, Baden-Württemberg bus, Hamburg) in README, sourced from blueprint §2.2
- [ ] Add a data dictionary noting license per source (CC BY-SA 4.0 for gtfs.de, DL-DE-BY-2.0 for VG250, ODbL for any Geofabrik use)
- [ ] Decide whether to pursue regional patch feeds (Phase 1 optional item) based on observed gap severity

---

**Explicitly out of scope / excluded per sourcing constraint:** Mobilithek, NAP.NRW, DB Developer API Marketplace, VVS/RMV live TRIAS APIs — all require registration (see blueprint §2.5).
