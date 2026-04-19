.PHONY: help setup fetch-static fetch-boundaries enrich-stops fetch-rt ingest \
        dbt-deps dbt-build dbt-test pipeline dagster dagster-rt dagster-static \
        dagster-boundaries app

help:
	@echo "setup              uv sync + create .env from .env.example"
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
	test -f .env || cp .env.example .env

fetch-static:
	uv run python ingestion/fetch_static_gtfs.py

fetch-boundaries:
	uv run python ingestion/fetch_admin_boundaries.py

enrich-stops:
	uv run python ingestion/enrich_stops_with_boundaries.py

fetch-rt:
	uv run python ingestion/fetch_rt.py

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
