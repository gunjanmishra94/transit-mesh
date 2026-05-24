# Single container for Render: runs the Streamlit dashboard (the one
# externally-reachable process, on $PORT) and dagster-daemon (schedules
# realtime_ingestion_job/static_gtfs_job against MotherDuck) side by side.
# See deploy/start.sh for how the two processes are supervised.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# curl: used by start.sh's self-ping loop to keep the Render free instance
# from sleeping. ca-certificates: duckdb's MotherDuck/https extension
# downloads need it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

COPY . .

# Bakes dbt_utils into the image so the container doesn't need a
# dbt-deps network round trip on every cold start (Render's free-tier
# filesystem doesn't persist dbt_packages/ across deploys anyway).
RUN cd dbt_transit && uv run --project .. --no-sync dbt deps --profiles-dir .

# Bakes target/manifest.json into the image too, against a throwaway local
# DuckDB file (dbt parse doesn't execute against the warehouse, so no
# MotherDuck token needed here). Without this, orchestrator/definitions.py
# runs `dbt parse` itself on first import — fine on a real machine, but on
# Render's free-tier 0.1 vCPU it was slow enough to blow dagster-daemon's
# code-server heartbeat timeout, crash-looping the grpc subprocess and
# starving Streamlit of CPU on the same instance.
RUN cd dbt_transit && DUCKDB_PATH=/tmp/dbt_parse.duckdb uv run --project .. --no-sync dbt parse --profiles-dir .

ENV PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/app/.dagster_home
RUN mkdir -p "$DAGSTER_HOME"

RUN chmod +x deploy/start.sh

EXPOSE 8501
CMD ["./deploy/start.sh"]
