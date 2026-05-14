.PHONY: help setup fetch-static fetch-boundaries enrich-stops fetch-rt ingest \
        dbt-deps dbt-build dbt-test pipeline dagster dagster-rt dagster-static \
        dagster-boundaries app

# Defaults to a pinned absolute local path — not relative, since dbt's own
# subprocess runs with cwd=dbt_transit/, so a relative value resolves against
# the wrong directory for that step. `?=` only applies this default when
# DUCKDB_PATH isn't already set in the calling environment, so CI (or anyone
# deploying against MotherDuck) can `DUCKDB_PATH=md:transit_mesh make ...`
# and have every target below honor it. This covers every target here EXCEPT
# the dagster-* targets — Dagster's own CLI auto-loads .env from the
# invocation directory instead, which is why `make setup` generates .env
# with an absolute path too (see .env.example).
export DUCKDB_PATH ?= $(CURDIR)/duckdb_data/transit.duckdb

help:
	@echo "setup              uv sync + generate .env with an absolute DUCKDB_PATH"
	@echo "fetch-static       download nationwide static GTFS"
	@echo "fetch-boundaries   download BKG VG250 admin boundaries"
	@echo "enrich-stops       point-in-polygon join stops -> boundaries"
	@echo "fetch-rt           poll the realtime GTFS-RT feed"
	@echo "ingest             run all four ingestion steps above, in order"
	@echo "dbt-deps           install dbt packages (dbt_utils)"
	@echo "dbt-build          dbt build (models + tests) in dbt_transit/"
	@echo "dbt-test           dbt test only"
	@echo "pipeline           ingest + dbt-build, end to end, no orchestrator"
	@echo "dagster            launch the Dagster UI (dagster dev)"
	@echo "dagster-rt         run realtime_ingestion_job once via the CLI"
	@echo "dagster-static     run static_gtfs_job once via the CLI"
	@echo "dagster-boundaries run admin_boundaries_job once via the CLI"
	@echo "app                launch the Streamlit dashboard"

setup:
	uv sync
	test -f .env || printf 'DUCKDB_PATH=%s/duckdb_data/transit.duckdb\n' "$(CURDIR)" > .env

# Run as `-m ingestion.x` (module mode, from repo root), not `python
# ingestion/x.py` (script mode) — orchestrator/definitions.py already imports
# these as `ingestion.x`, and duckdb_utils.py is a cross-file import within
# the package, which only resolves in module mode.
fetch-static:
	uv run python -m ingestion.fetch_static_gtfs

fetch-boundaries:
	uv run python -m ingestion.fetch_admin_boundaries

enrich-stops:
	uv run python -m ingestion.enrich_stops_with_boundaries

fetch-rt:
	uv run python -m ingestion.fetch_rt

ingest: fetch-static fetch-boundaries enrich-stops fetch-rt

dbt-deps:
	cd dbt_transit && uv run --project .. dbt deps --profiles-dir .

dbt-build:
	cd dbt_transit && uv run --project .. dbt build --profiles-dir .

dbt-test:
	cd dbt_transit && uv run --project .. dbt test --profiles-dir .

pipeline: ingest dbt-deps dbt-build

dagster: .dagster_home
	DAGSTER_HOME="$(CURDIR)/.dagster_home" uv run dagster dev -m orchestrator.definitions

dagster-rt: .dagster_home
	DAGSTER_HOME="$(CURDIR)/.dagster_home" uv run dagster job execute -m orchestrator.definitions -j realtime_ingestion_job

dagster-static: .dagster_home
	DAGSTER_HOME="$(CURDIR)/.dagster_home" uv run dagster job execute -m orchestrator.definitions -j static_gtfs_job

dagster-boundaries: .dagster_home
	DAGSTER_HOME="$(CURDIR)/.dagster_home" uv run dagster job execute -m orchestrator.definitions -j admin_boundaries_job

.dagster_home:
	mkdir -p .dagster_home

app:
	uv run streamlit run app/main.py
