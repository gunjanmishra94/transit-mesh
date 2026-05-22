# Transit Mesh — German Nationwide Transit Intelligence Platform

Spatial-temporal data platform tracking German public transport from country level down to village/stop level, built on GTFS-RT and static GTFS feeds.

**Stack:** DuckDB · dbt-duckdb · Dagster · Streamlit (PyDeck + Plotly)

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make setup      # uv sync + create .env
make pipeline   # ingest everything + dbt build, end to end
make app        # launch the Streamlit dashboard
```

`make dagster` launches the orchestrator UI for scheduled/on-demand runs. Run `make help` for the full list of targets.

## Deployed

- **Dashboard:** [transitmesh-de.streamlit.app](https://transitmesh-de.streamlit.app/)
- **Pipeline runs:** a `dagster-daemon` (see `Dockerfile`/`deploy/start.sh`) schedules realtime ingestion every minute and a static GTFS refresh daily, both building on a shared [MotherDuck](https://motherduck.com) database. Admin-boundary refreshes stay a manual [GitHub Actions](https://github.com/gunjanmishra94/transit-mesh/actions) trigger, since that job has no schedule either way.
