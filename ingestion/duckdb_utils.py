import time

import duckdb


def connect_with_retry(path, read_only=False, max_retries=5, base_delay=1.0):
    """duckdb.connect with retry — DuckDB is single-writer: no writer can open
    while any reader holds the file, and vice versa. The Streamlit dashboard
    and the every-minute realtime job both touch this file, so a transient
    lock conflict is expected, not exceptional.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return duckdb.connect(path, read_only=read_only)
        except duckdb.IOException as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(base_delay * attempt)
    raise last_error
