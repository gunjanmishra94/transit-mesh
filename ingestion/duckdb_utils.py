import os
import time

import duckdb


def _motherduck_config():
    # Passed explicitly via `config=` rather than relying on the motherduck
    # extension's own env-var auto-detection, whose exact casing
    # (`motherduck_token` vs `MOTHERDUCK_TOKEN`) isn't consistent across
    # docs/versions — checking both here and setting it explicitly works
    # regardless of which one the installed extension actually reads.
    token = os.environ.get("motherduck_token") or os.environ.get("MOTHERDUCK_TOKEN")
    return {"motherduck_token": token} if token else {}


def ensure_local_db_dir(path):
    """Create the DB file's parent directory if it has one. A no-op for a
    MotherDuck `md:...` database, which has no local directory component —
    `os.path.dirname` returns '' for those, and `os.makedirs('')` raises.
    """
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)


def connect_with_retry(path, read_only=False, max_retries=5, base_delay=1.0):
    """duckdb.connect with retry — DuckDB (including a MotherDuck `md:`
    database) is single-writer: no writer can open while any reader holds
    it, and vice versa. The Streamlit dashboard and the realtime ingestion
    job both touch this database, so a transient lock conflict is expected,
    not exceptional.
    """
    config = _motherduck_config() if str(path).startswith("md:") else {}
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return duckdb.connect(path, read_only=read_only, config=config)
        except duckdb.IOException as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(base_delay * attempt)
    raise last_error
