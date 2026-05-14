import os
import zipfile

import requests

from ingestion.duckdb_utils import connect_with_retry, ensure_local_db_dir

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")
STATIC_GTFS_URL = "https://download.gtfs.de/germany/free/latest.zip"
CACHE_DIR = os.getenv("GTFS_STATIC_CACHE_DIR", "ingestion/.cache/gtfs_static")
ZIP_PATH = os.path.join(CACHE_DIR, "latest.zip")

# Core GTFS tables needed for the staging models (blueprint §4.2).
# stop_times.txt / shapes.txt are deliberately excluded — they are large
# and not required by the current dbt models.
GTFS_FILES = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "calendar.txt"]


def download_static_gtfs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    with requests.get(STATIC_GTFS_URL, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(ZIP_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    return ZIP_PATH


def extract_gtfs_files(zip_path, extract_dir):
    extracted = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for filename in GTFS_FILES:
            if filename not in names:
                continue
            zf.extract(filename, extract_dir)
            extracted.append(filename)
    return extracted


def load_static_gtfs():
    zip_path = download_static_gtfs()
    extracted = extract_gtfs_files(zip_path, CACHE_DIR)

    ensure_local_db_dir(DB_PATH)
    conn = connect_with_retry(DB_PATH)

    row_counts = {}
    for filename in extracted:
        table_name = "raw_gtfs_" + filename.replace(".txt", "")
        file_path = os.path.join(CACHE_DIR, filename)
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT * FROM read_csv_auto(?, header=True, all_varchar=True)
        """, [file_path])
        row_counts[table_name] = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    conn.close()
    return row_counts


if __name__ == "__main__":
    counts = load_static_gtfs()
    for table_name, count in counts.items():
        print(f"{table_name}: {count} rows")
