# Transit Mesh — German Nationwide Transit Intelligence Platform

Local-first spatial-temporal data platform tracking German public transport from country level down to village/stop level.

See `project_blueprint.md` for the full architecture and data sourcing plan, and `TASKS.md` for the staged build plan.

## Stack

DuckDB · dbt-duckdb · Dagster · Streamlit (PyDeck + Plotly)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

## Data sources (all public, no registration — see `project_blueprint.md` §2)

- Realtime: `https://realtime.gtfs.de/realtime-free.pb`
- Static GTFS (nationwide): `https://download.gtfs.de/germany/free/latest.zip`
- Admin boundaries: BKG VG250
- Supplementary geodata: Geofabrik OSM Germany extracts

## Status

Scaffolding stage — see `TASKS.md` for what's built vs. pending.
