# Streamlit-only container for Render. Ingestion scheduling lives in
# GitHub Actions (see .github/workflows/), not here — an earlier attempt
# ran dagster-daemon in this same container to own scheduling instead, but
# a live realtime job (dbt build against MotherDuck, every minute) plus
# Streamlit blew past Render's free-tier 512MB and OOM-crash-looped the
# instance. app/main.py only reads from MotherDuck directly; it doesn't
# touch dbt_transit or orchestrator/, so this image doesn't need either.
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

ENV PYTHONUNBUFFERED=1

RUN chmod +x deploy/start.sh

EXPOSE 8501
CMD ["./deploy/start.sh"]
