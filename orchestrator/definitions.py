import os
from pathlib import Path

from dagster import (
    AssetKey,
    AssetOut,
    AssetSelection,
    Definitions,
    Output,
    ScheduleDefinition,
    asset,
    define_asset_job,
    multi_asset,
)
from dagster_dbt import DbtCliResource, dbt_assets

from ingestion.enrich_stops_with_boundaries import enrich_stops
from ingestion.fetch_admin_boundaries import load_admin_boundaries
from ingestion.fetch_rt import ingest_gtfs_rt
from ingestion.fetch_static_gtfs import load_static_gtfs

# Asset keys are namespaced ["transit", <table_name>] to match dagster-dbt's
# default key for dbt *sources* (source_name + table_name, see _sources.yml),
# so ingestion assets and the dbt model that reads them line up as one graph.
STATIC_GTFS_TABLES = ["raw_gtfs_agency", "raw_gtfs_stops", "raw_gtfs_routes", "raw_gtfs_trips", "raw_gtfs_calendar"]
VG250_TABLES = ["raw_vg250_states", "raw_vg250_districts", "raw_vg250_municipalities"]


@multi_asset(
    group_name="ingestion",
    outs={table: AssetOut(key=AssetKey(["transit", table])) for table in STATIC_GTFS_TABLES},
)
def static_gtfs_asset():
    """Downloads and loads the nationwide static GTFS feed (blueprint §2.1)."""
    counts = load_static_gtfs()
    for table in STATIC_GTFS_TABLES:
        yield Output(counts[table], output_name=table, metadata={"row_count": counts[table]})


@multi_asset(
    group_name="ingestion",
    outs={table: AssetOut(key=AssetKey(["transit", table])) for table in VG250_TABLES},
)
def admin_boundaries_asset():
    """Downloads and loads BKG VG250 administrative boundaries (blueprint §2.4)."""
    counts = load_admin_boundaries()
    for table in VG250_TABLES:
        yield Output(counts[table], output_name=table, metadata={"row_count": counts[table]})


@asset(
    key=AssetKey(["transit", "stg_gtfs_stops_enriched"]),
    group_name="ingestion",
    deps=[
        AssetKey(["transit", "raw_gtfs_stops"]),
        AssetKey(["transit", "raw_vg250_states"]),
        AssetKey(["transit", "raw_vg250_districts"]),
        AssetKey(["transit", "raw_vg250_municipalities"]),
    ],
)
def stg_gtfs_stops_enriched_asset():
    """Point-in-polygon joins GTFS stops to VG250 boundaries (blueprint §2.4)."""
    total, matched = enrich_stops()
    return Output(matched, metadata={"total_stops": total, "matched": matched, "match_rate": matched / total})


@multi_asset(
    group_name="ingestion",
    outs={
        "raw_trip_updates": AssetOut(key=AssetKey(["transit", "raw_trip_updates"])),
        "raw_service_alerts": AssetOut(key=AssetKey(["transit", "raw_service_alerts"])),
    },
)
def raw_gtfs_rt_asset():
    """Polls gtfs.de real-time protobuf feed (blueprint §2.1)."""
    n_trip_updates, n_alerts = ingest_gtfs_rt()
    yield Output(n_trip_updates, output_name="raw_trip_updates", metadata={"row_count": n_trip_updates})
    yield Output(n_alerts, output_name="raw_service_alerts", metadata={"row_count": n_alerts})


DBT_PROJECT_DIR = Path(__file__).parent.parent / "dbt_transit"
dbt_resource = DbtCliResource(project_dir=os.fspath(DBT_PROJECT_DIR))

# @dbt_assets needs a manifest.json; generate one at module load if it's
# missing so `dagster dev` works without a manual `dbt parse` step first.
dbt_manifest_path = DBT_PROJECT_DIR / "target" / "manifest.json"
if not dbt_manifest_path.exists():
    dbt_resource.cli(["parse"], target_path=Path("target")).wait()


@dbt_assets(manifest=dbt_manifest_path)
def dbt_transit_assets(context, dbt: DbtCliResource):
    # "build" (not "run") so the dbt tests dbt_assets exposes as asset checks
    # actually execute — "run" only builds models and leaves them unevaluated.
    yield from dbt.cli(["build"], context=context).stream()


# Realtime is the frequent path — every-minute polling, matching the RT
# feed's own ~10-30s update cadence.
realtime_job = define_asset_job(
    "realtime_ingestion_job",
    selection=AssetSelection.assets(raw_gtfs_rt_asset) | AssetSelection.assets(dbt_transit_assets),
)
realtime_schedule = ScheduleDefinition(job=realtime_job, cron_schedule="* * * * *")

# Static GTFS is a full daily snapshot from DELFI (blueprint §2.1).
static_gtfs_job = define_asset_job(
    "static_gtfs_job",
    selection=(
        AssetSelection.assets(static_gtfs_asset)
        | AssetSelection.assets(stg_gtfs_stops_enriched_asset)
        | AssetSelection.assets(dbt_transit_assets)
    ),
)
static_gtfs_schedule = ScheduleDefinition(job=static_gtfs_job, cron_schedule="0 3 * * *")

# VG250 boundaries update roughly annually — no cron schedule; trigger this
# job manually from the Dagster UI when a new VG250 release comes out.
admin_boundaries_job = define_asset_job(
    "admin_boundaries_job",
    selection=(
        AssetSelection.assets(admin_boundaries_asset)
        | AssetSelection.assets(stg_gtfs_stops_enriched_asset)
        | AssetSelection.assets(dbt_transit_assets)
    ),
)

defs = Definitions(
    assets=[
        static_gtfs_asset,
        admin_boundaries_asset,
        stg_gtfs_stops_enriched_asset,
        raw_gtfs_rt_asset,
        dbt_transit_assets,
    ],
    resources={"dbt": dbt_resource},
    jobs=[realtime_job, static_gtfs_job, admin_boundaries_job],
    schedules=[realtime_schedule, static_gtfs_schedule],
)
