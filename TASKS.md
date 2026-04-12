# Build Tasks: German Nationwide Transit Intelligence Platform

Staged implementation plan derived from `project_blueprint.md`. Work top to bottom — each phase produces something runnable before the next begins.

---

## Phase 0 — Repo Scaffolding

- [x] Init project structure per blueprint §3 (Directory Structure): `ingestion/`, `dbt_transit/`, `orchestrator/`, `app/`, `duckdb_data/`
- [x] `pyproject.toml` with deps: `duckdb`, `dbt-duckdb`, `dagster`, `dagster-webserver`, `streamlit`, `pydeck`, `plotly`, `requests`, `gtfs-realtime-bindings` (managed with `uv`, see `uv.lock`)
- [x] `.env` + `.env.example` (DB path, any config — no API keys needed per §2 sourcing constraint)
- [x] `README.md` with setup/run instructions
- [x] `.gitignore` (`duckdb_data/`, `.env`, `dbt_transit/target/`, `dbt_transit/logs/`)
- [x] Initialize git repo, first commit

## Phase 1 — Static Nationwide Baseline (do this before realtime)

Static GTFS is the structural backbone for "every place in Germany" — build this first so downstream models have a complete stop/route/agency universe even before realtime data flows.

- [x] `ingestion/fetch_static_gtfs.py` — download `https://download.gtfs.de/germany/free/latest.zip`, unzip, bulk-load `stops.txt`, `routes.txt`, `trips.txt`, `calendar.txt`, `agency.txt` into DuckDB raw tables (verified live: 688K stops, 24.9K routes, 1.9M trips, 459 agencies)
- [x] `ingestion/fetch_admin_boundaries.py` — download BKG VG250 (Länder/Kreise/Gemeinden), load into a spatial reference table via DuckDB `spatial` extension (verified live: 16 states, 401 districts, 10,939 municipalities; geom in EPSG:25832)
- [x] Point-in-polygon join: enrich `raw_stops` with `municipality_name` / `district_id` / `state_name` from VG250 (`ingestion/enrich_stops_with_boundaries.py` → `stg_gtfs_stops_enriched`; 98.9% match rate, remainder are cross-border stops)
- [x] Sanity check: row counts per Bundesland, confirm no state has zero stops (all 16 states represented, 2,656–135,699 stops each)
- [ ] (Optional, later) `ingestion/fetch_regional_gtfs.py` for VVS/HVV/MVV/etc. static feeds to patch gaps — defer until Phase 1 baseline is validated

## Phase 2 — Realtime Ingestion

- [x] `ingestion/fetch_rt.py` per blueprint §4.1 — poll `realtime-free.pb`, parse TripUpdates, write to `raw_trip_updates` (rewritten: blueprint's `conn.register(list_of_dicts)` doesn't actually work on current DuckDB — fixed by building a `pandas.DataFrame` first)
- [x] Extend parser for ServiceAlerts entities → `raw_service_alerts` (verified live: 43,250 alerts)
- [x] Manual test run: confirmed live — 383,524 trip update events, 33,917 distinct trips, delays in a sane range (avg ~90s, min -7140s/max 11460s). **Finding: `route_id` is empty on every RT entity in this feed** — route/agency must be resolved downstream via a `trip_id` join against static `trips.txt`, not read off the RT feed directly.
- [x] ~~Add a `source_agency` / `feed_coverage_flag` column~~ — superseded by the finding above: agency resolution and coverage tracking both happen downstream in dbt (`mrt_rt_coverage_by_agency`, Phase 3) via `trip_id → raw_gtfs_trips.route_id → raw_gtfs_routes.agency_id`, not as a column baked into raw ingestion. Added `feed_timestamp` (feed generation time) and `entity_id` instead, for staleness/dedup checks.

## Phase 3 — dbt Modeling

- [x] `dbt_transit/dbt_project.yml`, `profiles.yml` (duckdb adapter, path to `duckdb_data/transit.duckdb`; also added `packages.yml` for `dbt_utils`)
- [x] Staging: `stg_gtfs__stops` (reads the pre-built `stg_gtfs_stops_enriched`), `stg_gtfs__routes`, `stg_gtfs__agency`, `stg_gtfs__trips`, `stg_rt__trip_updates` (drops `route_id` — always empty, see Phase 2 finding)
- [x] Intermediate: `int_trip_delays_enriched` (joins RT → `stg_gtfs__trips` → `stg_gtfs__routes` for agency, → `stg_gtfs__stops` for geography)
- [x] Marts: `mrt_performance_by_stop`, `mrt_performance_by_municipality`, `mrt_performance_national`
- [x] New mart: `mrt_rt_coverage_by_agency` — verified live: 142 agencies have scheduled trips but zero RT observations in the trailing 24h, now visible instead of silently reading as "on time"
- [x] dbt tests: not-null/unique/relationships on keys, `dbt_utils.accepted_range` on delay minutes (widened to -120..300 for the per-stop mart — single-poll per-stop averages can legitimately be one real ~80min-early observation, not a smoothed average) and 0..100 on coverage pct
- [x] `dbt run` + `dbt test` clean pass — 10 models, 17 tests, all green

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
