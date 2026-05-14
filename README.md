# Transit Mesh — German Nationwide Transit Intelligence Platform

Local-first spatial-temporal data platform tracking German public transport from country level down to village/stop level.

See `project_blueprint.md` for the full architecture and data sourcing plan, and `TASKS.md` for the staged build plan.

## Stack

DuckDB · dbt-duckdb · Dagster · Streamlit (PyDeck + Plotly)

## Setup

Requires [uv](https://docs.astral.sh/uv/) and `make`.

```bash
make setup      # uv sync + create .env
make pipeline   # ingest everything + dbt build, end to end (no orchestrator)
make app        # launch the Streamlit dashboard
```

Run `make help` for the full list of targets. Individual steps (`make fetch-static`, `make fetch-rt`, `make dbt-build`, ...) are also available if you want to run the pipeline one stage at a time — see `Makefile`.

## Orchestration (Dagster)

```bash
make dagster        # launch the Dagster UI at localhost:3000
make dagster-rt      # run realtime_ingestion_job once via the CLI
make dagster-static  # run static_gtfs_job once via the CLI
```

Jobs: `realtime_ingestion_job` (every minute — RT polling + dbt), `static_gtfs_job` (daily 03:00 — static GTFS + stop enrichment + dbt), `admin_boundaries_job` (manual trigger only — VG250 updates ~annually).

## Dashboard (Streamlit)

```bash
make app
```

Map / Performance / Trends / Coverage tabs, with a state → district → municipality drill-down in the sidebar.

## Deployment (free)

The local stack above (Dagster daemon + local DuckDB file) doesn't fit any
free host — there's no persistent-background-worker free tier, and the
local `transit.duckdb` file is multiple GB. The free deploy instead swaps
two pieces:

| Local | Free deploy |
|---|---|
| Local DuckDB file | [MotherDuck](https://motherduck.com) (free tier) — `DUCKDB_PATH=md:transit_mesh` |
| Dagster daemon (`* * * * *` / daily schedules) | GitHub Actions (`.github/workflows/`) on the same cadence, best-effort |
| `make app` on your machine | [Streamlit Community Cloud](https://streamlit.io/cloud) (free) |

Setup, once:

1. Create a free [MotherDuck](https://app.motherduck.com) account and a
   database named `transit_mesh`. Grab a token from Settings -> Tokens.
2. **Bootstrap the database once, locally** — the scheduled workflows below
   only *refresh* tables, and `enrich_stops_with_boundaries` needs both
   static GTFS stops and VG250 boundaries to already exist the first time:
   ```bash
   DUCKDB_PATH=md:transit_mesh MOTHERDUCK_TOKEN=<your-token> make pipeline
   ```
3. In the GitHub repo, add `MOTHERDUCK_TOKEN` as an Actions secret (Settings
   -> Secrets and variables -> Actions -> New repository secret).
4. From then on, three workflows keep MotherDuck fresh — all read-only to
   debug, since each run's log and `dbt build` summary show up under the
   Actions tab, plus uploaded `manifest.json`/`run_results.json`/`dbt.log`
   artifacts on every run:
   - `rt-ingestion.yml` — every 15 min, GTFS-RT poll + `dbt build`.
   - `static-gtfs.yml` — daily at 03:17, static GTFS refresh + `dbt build`.
   - `admin-boundaries.yml` — manual only (`workflow_dispatch`), VG250
     updates ~annually.

   All three share a `motherduck-writer` concurrency group so they queue
   instead of racing each other for the single-writer database lock.
5. Deploy `app/main.py` to Streamlit Community Cloud pointed at this repo
   (`requirements.txt` at the repo root is scoped for it — see the comment
   in that file for why it's separate from `pyproject.toml`). In the app's
   Secrets editor, set the keys shown in `.streamlit/secrets.toml.example`
   (`DUCKDB_PATH=md:transit_mesh` + your MotherDuck token, both env-var
   casings).

Local dev (`make app`, `make pipeline`, `make dagster*`) is unaffected —
`DUCKDB_PATH` still defaults to the local file when unset.

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
