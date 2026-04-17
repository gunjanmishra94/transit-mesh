# Transit Mesh — German Nationwide Transit Intelligence Platform

Local-first spatial-temporal data platform tracking German public transport from country level down to village/stop level.

See `project_blueprint.md` for the full architecture and data sourcing plan, and `TASKS.md` for the staged build plan.

## Stack

DuckDB · dbt-duckdb · Dagster · Streamlit (PyDeck + Plotly)

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

Run scripts with `uv run python ingestion/fetch_static_gtfs.py`, etc.

## Orchestration (Dagster)

```bash
export DAGSTER_HOME="$(pwd)/.dagster_home"  # local run/event storage, gitignored
uv run dagster dev -m orchestrator.definitions
```

Jobs: `realtime_ingestion_job` (every minute — RT polling + dbt), `static_gtfs_job` (daily 03:00 — static GTFS + stop enrichment + dbt), `admin_boundaries_job` (manual trigger only — VG250 updates ~annually).

## Dashboard (Streamlit)

```bash
uv run streamlit run app/main.py
```

Map / Performance / Trends / Coverage tabs, with a state → district → municipality drill-down in the sidebar.

## Data sources (all public, no registration — see `project_blueprint.md` §2)

| Source | License | Cadence |
|---|---|---|
| Realtime: `https://realtime.gtfs.de/realtime-free.pb` | CC BY-SA 4.0 (+ per-agency) | ~10-30s |
| Static GTFS (nationwide): `https://download.gtfs.de/germany/free/latest.zip` | CC BY-SA 4.0 | Daily |
| Admin boundaries: BKG VG250 | DL-DE-BY-2.0 (attribution required) | ~Annual |
| Supplementary geodata: Geofabrik OSM Germany extracts | ODbL 1.0 (attribution + share-alike on derived DBs) | Rolling |

Any output derived from these (dashboards, exports) must carry attribution per the licenses above — this isn't public-domain data, just registration-free.

## Known limitations

- **Realtime coverage is genuinely partial, not just "not yet backfilled."** As of the last full pipeline run, **140 of 459 agencies (30.5%) have scheduled trips but zero realtime observations** in the trailing 24h — see the Coverage tab in the dashboard or query `mrt_rt_coverage_by_agency` directly. This matches the documented gaps in `realtime-free.pb`: incomplete bus coverage in Rhein-Ruhr and Baden-Württemberg, Hamburg (Stadtwerke Hamburg) license questions pending, and partial reliance on foreign feeds near borders (project_blueprint.md §2.2).
- **Regional static GTFS patch feeds (Phase 1's optional item) are not implemented.** Static stop-matching against VG250 boundaries is already 98.9% complete (project_blueprint.md §2.4 / TASKS.md Phase 1), so there's no static-data quality problem to justify pulling in per-Verkehrsverbund GTFS ZIPs right now.
- **The RT coverage gap can't be closed within the no-registration constraint.** The obvious way to fill it — per-agency live RT/TRIAS APIs (e.g. VVS, RMV) — requires account registration, which this project explicitly excludes (project_blueprint.md §2.5). Treat the 30.5% dark-agency figure as a structural limit of the public/no-registration data source set, not a bug to fix, and re-evaluate only if the registration constraint itself changes.

## Status

Phases 0-6 (scaffolding through Streamlit dashboard) complete — see `TASKS.md` for details.
