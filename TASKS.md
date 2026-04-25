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

- [x] `orchestrator/definitions.py`: `raw_gtfs_rt_asset` (multi-asset, outputs `raw_trip_updates` + `raw_service_alerts`), every-minute schedule
- [x] Add `static_gtfs_asset` (multi-asset, 5 static tables), daily 03:00 schedule
- [x] Add `admin_boundaries_asset` (multi-asset, 3 VG250 tables) + `stg_gtfs_stops_enriched_asset`, manual-trigger job (no cron — VG250 updates ~annually)
- [x] Wire dbt run as a downstream asset dependency (dagster-dbt) — ingestion assets use `AssetKey(["transit", table])`, matching dagster-dbt's default key for dbt sources, so the whole graph (ingestion → staging → intermediate → marts) connects automatically; `@dbt_assets` runs `dbt build` (not `run`) so dbt tests execute as Dagster asset checks
- [x] Verified: `dagster definitions validate` passes; full asset graph printed and confirmed wired correctly; `realtime_ingestion_job` and `static_gtfs_job` both executed end-to-end via `dagster job execute` (27/27 steps pass: 10 models + 17 tests-as-checks)

## Phase 5 — Streamlit App

- [x] `app/main.py` per blueprint §4.4 — state → district → municipality drill-down (4 tabs: Map, Performance, Trends, Coverage)
- [x] Add coverage indicator (from `mrt_rt_coverage_by_agency`) — warning banner up top + dedicated Coverage tab; also required adding `stop_lat`/`stop_lon`/`municipality_id` to `int_trip_delays_enriched` and the by_stop/by_municipality marts (municipality centroid computed from distinct stops, not observation-weighted)
- [x] PyDeck map layer — municipality centroids nationwide, stop-level scatter when a state/district is selected, colored green→red by avg delay
- [x] Plotly time-series panel — delay over polling history (`date_trunc('minute', ingested_at)`) for the current selection; degrades to a plain table + notice when only one poll exists so far
- [x] Smoke test: **no browser available in this environment** — verified instead by (1) running the dbt build clean after the schema changes, (2) starting the app headlessly and confirming no server-side exceptions on load, (3) directly executing every drill-down branch's SQL (state-level, district-level, municipality-level, trend) against real data, and (4) directly testing the empty-result edge case (nonexistent state/district) for the map/bar-chart/trend code paths — all confirmed non-crashing. Visual/interactive confirmation in an actual browser is still outstanding.

## Phase 6 — Data Quality & Gap Documentation

- [x] Document known coverage gaps in README, backed by live numbers: 140/459 agencies (30.5%) have scheduled trips but zero RT observations in the trailing 24h, matching the documented Rhein-Ruhr/Baden-Württemberg/Hamburg gaps (blueprint §2.2)
- [x] Add a license/cadence table per source to README (CC BY-SA 4.0 for gtfs.de, DL-DE-BY-2.0 for VG250, ODbL for Geofabrik)
- [x] Decision: **not pursuing regional static patch feeds** — static stop-matching is already 98.9% complete, so there's no static data-quality gap to justify it. The RT coverage gap is structural (closing it needs registration-gated per-agency APIs, explicitly out of scope per §2.5) and is documented as a known limitation instead of chased further.

## Phase 7 — Extended Analytics (post-launch additions)

- [x] Live dashboard auto-refresh: coverage banner + all tabs wrapped in `@st.fragment(run_every="30s")` so the dashboard reflects new data from the every-minute realtime job without a manual browser reload
- [x] Mode-of-transport breakdown: `route_type`/`route_type_label` (new `macros/route_type_label.sql`) wired through `int_trip_delays_enriched`; new `mrt_performance_by_mode` mart (national) + Mode tab with grouped bar charts (avg/median/p90 + % delayed by Bus/Rail/Tram/Subway/Ferry)
- [x] Worst-performing routes: new `mrt_performance_by_route` mart (min. 20 observations to filter noise) + Routes tab with a sortable ranking table
- [x] Fixed the "average delay doesn't make sense for a big city" problem: added `median_delay_minutes` and `p90_delay_minutes` (DuckDB `MEDIAN`/`QUANTILE_CONT`) to `mrt_performance_national` and `mrt_performance_by_municipality`, surfaced alongside average everywhere in the Performance tab instead of average alone; added a SQL-binned (not pandas-side) delay-distribution histogram to the Trends tab so the actual shape is visible, not just one point estimate
- [x] Verified with `streamlit.testing.v1.AppTest` (not a plain `curl` check — that only fetches the static HTML shell and never triggers real script execution): zero exceptions through the full state → district drill-down, the Routes sort selectbox, and all four new/changed tabs; `dbt build --full-refresh` passes 35/35 (up from 27) after the schema changes

---

**Explicitly out of scope / excluded per sourcing constraint:** Mobilithek, NAP.NRW, DB Developer API Marketplace, VVS/RMV live TRIAS APIs — all require registration (see blueprint §2.5).
