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

- Realtime: `https://realtime.gtfs.de/realtime-free.pb`
- Static GTFS (nationwide): `https://download.gtfs.de/germany/free/latest.zip`
- Admin boundaries: BKG VG250
- Supplementary geodata: Geofabrik OSM Germany extracts

## Status

Scaffolding stage — see `TASKS.md` for what's built vs. pending.
