import os
import zipfile

import duckdb
import requests

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


def download_vg250():
    os.makedirs(CACHE_DIR, exist_ok=True)
    with requests.get(VG250_URL, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(ZIP_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    return ZIP_PATH


def extract_geopackage(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extract(GPKG_MEMBER, extract_dir)
    return os.path.join(extract_dir, GPKG_MEMBER)


def load_admin_boundaries():
    zip_path = download_vg250()
    gpkg_path = extract_geopackage(zip_path, CACHE_DIR)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = duckdb.connect(DB_PATH)
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
