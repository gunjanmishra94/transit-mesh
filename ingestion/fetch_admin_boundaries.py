import os
import time
import zipfile

import requests

from ingestion.duckdb_utils import connect_with_retry, ensure_local_db_dir

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")
VG250_URL = "https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/aktuell/vg250_01-01.utm32s.gpkg.ebenen.zip"
CACHE_DIR = os.getenv("VG250_CACHE_DIR", "ingestion/.cache/vg250")
ZIP_PATH = os.path.join(CACHE_DIR, "vg250.zip")
GPKG_MEMBER = "vg250_ebenen_0101/DE_VG250.gpkg"

# GF=4 selects the combined land+water polygon (one row per administrative
# unit) — VG250 also ships border-only (GF=2) and water-only (GF=3) variants
# of the same units, which would otherwise duplicate rows.
LAYERS = {
    "vg250_lan": "raw_vg250_states",
    "vg250_krs": "raw_vg250_districts",
    "vg250_gem": "raw_vg250_municipalities",
}


def _download_attempt():
    # The ~67MB download has been observed dropping mid-stream (different
    # byte offset each time, consistent with a connection-duration limit
    # rather than a fixed-size one) — resume via Range on retry instead of
    # restarting from scratch.
    existing_size = os.path.getsize(ZIP_PATH) if os.path.exists(ZIP_PATH) else 0
    headers = {"Range": f"bytes={existing_size}-"} if existing_size else {}

    with requests.get(VG250_URL, stream=True, timeout=180, headers=headers) as response:
        if response.status_code == 416:
            # Requested range starts at/past the resource's end — the cached
            # file is already the complete download, nothing left to fetch.
            return
        if existing_size and response.status_code == 200:
            # Server ignored the Range request and is sending the full file again.
            existing_size = 0
        response.raise_for_status()
        mode = "ab" if response.status_code == 206 else "wb"
        content_length = int(response.headers.get("Content-Length", 0))
        with open(ZIP_PATH, mode) as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)

    final_size = os.path.getsize(ZIP_PATH)
    expected_size = existing_size + content_length if content_length else None
    if expected_size and final_size != expected_size:
        raise IOError(f"Incomplete download: got {final_size} bytes, expected {expected_size}")


def download_vg250(max_retries=4):
    os.makedirs(CACHE_DIR, exist_ok=True)
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            _download_attempt()
            return ZIP_PATH
        except (requests.exceptions.RequestException, IOError) as e:
            last_error = e
            print(f"Download attempt {attempt}/{max_retries} failed: {e}")
            time.sleep(min(2 ** attempt, 15))
    raise last_error


def extract_geopackage(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extract(GPKG_MEMBER, extract_dir)
    return os.path.join(extract_dir, GPKG_MEMBER)


def load_admin_boundaries():
    zip_path = download_vg250()
    gpkg_path = extract_geopackage(zip_path, CACHE_DIR)

    ensure_local_db_dir(DB_PATH)
    conn = connect_with_retry(DB_PATH)
    conn.execute("INSTALL spatial; LOAD spatial;")

    row_counts = {}
    for source_layer, table_name in LAYERS.items():
        # geom is UTM32s (EPSG:25832), matching the source file — transform
        # to WGS84 happens at the point-in-polygon join with GTFS stops.
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT
                AGS AS official_key,
                ARS AS regional_key,
                GEN AS name,
                BEZ AS designation,
                SN_L AS state_code,
                geom
            FROM st_read(?, layer=?)
            WHERE GF = 4
        """, [gpkg_path, source_layer])
        row_counts[table_name] = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    conn.close()
    return row_counts


if __name__ == "__main__":
    counts = load_admin_boundaries()
    for table_name, count in counts.items():
        print(f"{table_name}: {count} rows")
