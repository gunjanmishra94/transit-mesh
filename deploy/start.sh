#!/usr/bin/env bash
# Runs the Streamlit dashboard on Render. Ingestion scheduling is handled
# by GitHub Actions, not this container (see .github/workflows/ and the
# Dockerfile's top comment for why).
set -euo pipefail

# Self-ping: Render's free-tier sleep timer only resets on inbound traffic
# to the public URL, not on internal activity — so this loop pings the
# service's own external URL (Render sets RENDER_EXTERNAL_URL
# automatically) to keep it awake. Trades most of the 750 free monthly
# instance-hours for zero cold starts, which only works if this is the
# *only* always-on service on the account.
if [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    (
        while true; do
            sleep 60
            curl -fsS -o /dev/null "$RENDER_EXTERNAL_URL" || true
        done
    ) &
fi

exec uv run --no-sync streamlit run app/main.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true
