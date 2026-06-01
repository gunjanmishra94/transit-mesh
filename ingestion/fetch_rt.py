import os
from datetime import datetime, timezone

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2

from ingestion.duckdb_utils import connect_with_retry, ensure_local_db_dir

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")
RT_URL = "https://realtime.gtfs.de/realtime-free.pb"


def fetch_feed():
    response = requests.get(RT_URL, timeout=30)
    response.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def parse_trip_updates(feed, feed_timestamp, ingested_at):
    # NB: this feed leaves TripDescriptor.route_id empty on every entity,
    # route/agency must be resolved downstream via a join on trip_id against
    # the static GTFS trips.txt, not read directly off the RT feed.
    records = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        route_id = tu.trip.route_id

        for su in tu.stop_time_update:
            records.append({
                "entity_id": entity.id,
                "trip_id": trip_id,
                "route_id": route_id,
                "stop_id": su.stop_id,
                "arrival_delay_sec": su.arrival.delay if su.HasField("arrival") else None,
                "departure_delay_sec": su.departure.delay if su.HasField("departure") else None,
                "feed_timestamp": feed_timestamp,
                "ingested_at": ingested_at,
            })
    return records


def parse_service_alerts(feed, feed_timestamp, ingested_at):
    records = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        route_ids = [ie.route_id for ie in alert.informed_entity if ie.route_id]
        stop_ids = [ie.stop_id for ie in alert.informed_entity if ie.stop_id]
        agency_ids = [ie.agency_id for ie in alert.informed_entity if ie.agency_id]

        records.append({
            "entity_id": entity.id,
            "cause": gtfs_realtime_pb2.Alert.Cause.Name(alert.cause),
            "effect": gtfs_realtime_pb2.Alert.Effect.Name(alert.effect),
            "header_text": alert.header_text.translation[0].text if alert.header_text.translation else None,
            "description_text": alert.description_text.translation[0].text if alert.description_text.translation else None,
            "route_ids": ",".join(route_ids) or None,
            "stop_ids": ",".join(stop_ids) or None,
            "agency_ids": ",".join(agency_ids) or None,
            "feed_timestamp": feed_timestamp,
            "ingested_at": ingested_at,
        })
    return records


def ingest_gtfs_rt():
    feed = fetch_feed()
    feed_timestamp = datetime.fromtimestamp(feed.header.timestamp, tz=timezone.utc) if feed.header.timestamp else None
    ingested_at = datetime.now(timezone.utc)

    trip_update_records = parse_trip_updates(feed, feed_timestamp, ingested_at)
    alert_records = parse_service_alerts(feed, feed_timestamp, ingested_at)

    ensure_local_db_dir(DB_PATH)
    conn = connect_with_retry(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_trip_updates (
            entity_id VARCHAR,
            trip_id VARCHAR,
            route_id VARCHAR,
            stop_id VARCHAR,
            arrival_delay_sec INTEGER,
            departure_delay_sec INTEGER,
            feed_timestamp TIMESTAMPTZ,
            ingested_at TIMESTAMPTZ
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_service_alerts (
            entity_id VARCHAR,
            cause VARCHAR,
            effect VARCHAR,
            header_text VARCHAR,
            description_text VARCHAR,
            route_ids VARCHAR,
            stop_ids VARCHAR,
            agency_ids VARCHAR,
            feed_timestamp TIMESTAMPTZ,
            ingested_at TIMESTAMPTZ
        )
    """)

    if trip_update_records:
        df_trip_updates = pd.DataFrame(trip_update_records)
        conn.register("df_trip_updates", df_trip_updates)
        conn.execute("INSERT INTO raw_trip_updates SELECT * FROM df_trip_updates")

    if alert_records:
        df_alerts = pd.DataFrame(alert_records)
        conn.register("df_alerts", df_alerts)
        conn.execute("INSERT INTO raw_service_alerts SELECT * FROM df_alerts")

    conn.close()
    return len(trip_update_records), len(alert_records)


if __name__ == "__main__":
    n_trip_updates, n_alerts = ingest_gtfs_rt()
    print(f"Ingested {n_trip_updates} trip update events and {n_alerts} service alerts.")
