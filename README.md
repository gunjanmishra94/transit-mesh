# Transit Mesh, German Nationwide Transit Intelligence Platform

Spatial-temporal data platform tracking German public transport from country level down to village/stop level, built on GTFS-RT and static GTFS feeds.

**Stack:** Python · SQL · DuckDB · MotherDuck · dbt · Dagster · Streamlit (PyDeck + Plotly) · GitHub Actions

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
- **Pipeline runs (GitHub Actions):** [github.com/gunjanmishra94/transit-mesh/actions](https://github.com/gunjanmishra94/transit-mesh/actions), realtime ingestion every 5 min, static GTFS refresh daily, both building on a shared [MotherDuck](https://motherduck.com) database. Triggered by a small Cloudflare Worker (`cron-trigger/`) via `repository_dispatch`, since GitHub's native `schedule:` trigger is unreliable at this frequency — see `cron-trigger/README.md`.
