#!/usr/bin/env bash
# Runs dagster-daemon (schedules) and the Streamlit dashboard side by side
# in one Render instance. Only Streamlit is exposed externally (Render
# forwards a single port) — the daemon needs no inbound traffic, just the
# container to stay alive, which Streamlit being reachable guarantees.
#
# If either process dies, `wait -n` returns and this script exits, taking
# the whole container down — Render then restarts it fresh, bringing both
# processes back up together rather than leaving one half running alone.
set -euo pipefail

export DAGSTER_HOME="${DAGSTER_HOME:-/app/.dagster_home}"
mkdir -p "$DAGSTER_HOME"

uv run --no-sync dagster-daemon run -m orchestrator.definitions &
DAEMON_PID=$!

uv run --no-sync streamlit run app/main.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true &
STREAMLIT_PID=$!

# Self-ping: Render's free-tier sleep timer only resets on inbound traffic
# to the public URL, not on internal activity — so this loop pings the
# service's own external URL (Render sets RENDER_EXTERNAL_URL
# automatically) to keep it awake. See project chat history: this trades
# most of the 750 free monthly instance-hours for zero cold starts, which
# only works if this is the *only* always-on service on the account.
if [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    (
        while true; do
            sleep 60
            curl -fsS -o /dev/null "$RENDER_EXTERNAL_URL" || true
        done
    ) &
fi

trap 'kill -TERM "$DAEMON_PID" "$STREAMLIT_PID" 2>/dev/null || true' TERM INT

wait -n "$DAEMON_PID" "$STREAMLIT_PID"
EXIT_CODE=$?
kill -TERM "$DAEMON_PID" "$STREAMLIT_PID" 2>/dev/null || true
exit "$EXIT_CODE"
