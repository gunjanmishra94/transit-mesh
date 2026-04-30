import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import plotly.express as px
import pydeck as pdk
import streamlit as st

# Explicit rather than relying on how `streamlit run` sets up sys.path: this
# script needs the sibling `ingestion` package, and Streamlit's own script
# loader isn't guaranteed to put the repo root on the path the way `python -m`
# does (this bit us for the ingestion scripts themselves — see Makefile).
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingestion.duckdb_utils import connect_with_retry  # noqa: E402

st.set_page_config(page_title="German Transit Intelligence", layout="wide")

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")


@contextmanager
def get_db_connection():
    # Deliberately not cached/persistent: DuckDB is single-writer, and no
    # writer (Dagster's ingestion jobs, dbt build) can open the file at all
    # while ANY reader has it open — a persistent connection held for the
    # life of the browser session would permanently block the pipeline.
    # Opening fresh per query batch and closing immediately keeps the lock
    # window down to milliseconds instead of "as long as the tab is open."
    # connect_with_retry absorbs the residual race where a writer (e.g. the
    # every-minute realtime job) happens to hold the file at that instant.
    conn = connect_with_retry(DB_PATH, read_only=True, max_retries=4, base_delay=0.5)
    try:
        yield conn
    finally:
        conn.close()


try:
    with get_db_connection() as _conn:
        _conn.execute("SELECT 1 FROM mrt_performance_national LIMIT 1")
except Exception as e:
    if not os.path.exists(DB_PATH):
        st.error(
            "DuckDB file not found — the pipeline hasn't run yet. "
            "Run ingestion + `dbt build` first (see README)."
        )
    else:
        st.error(
            f"Could not open the database after retrying — it may be held by a "
            f"long-running write (a full `make pipeline` run, for example). "
            f"Try reloading in a few seconds.\n\nDetails: {e}"
        )
    st.stop()

st.title("🇩🇪 Nationwide Transit Intelligence Platform")
st.markdown("Real-time telemetry, delay propagation, and spatial analytics from country to village level.")

# --- Sidebar drill-down, shared across tabs ---
st.sidebar.header("Spatial Drill-Down")
with get_db_connection() as conn:
    states = [r[0] for r in conn.execute(
        "SELECT DISTINCT state_name FROM mrt_performance_by_municipality WHERE state_name IS NOT NULL ORDER BY 1"
    ).fetchall()]
selected_state = st.sidebar.selectbox("Bundesland", ["All Germany"] + states)

selected_district = "All Districts"
if selected_state != "All Germany":
    with get_db_connection() as conn:
        districts = [r[0] for r in conn.execute(
            "SELECT DISTINCT district_name FROM mrt_performance_by_municipality "
            "WHERE state_name = ? AND district_name IS NOT NULL ORDER BY 1",
            [selected_state],
        ).fetchall()]
    selected_district = st.sidebar.selectbox("Landkreis", ["All Districts"] + districts)

st.sidebar.header("Filters")
with get_db_connection() as conn:
    modes = [r[0] for r in conn.execute(
        "SELECT route_type_label FROM mrt_performance_by_mode ORDER BY route_type_label"
    ).fetchall()]
selected_mode = st.sidebar.selectbox("Mode of Transport", ["All Modes"] + modes)
st.sidebar.caption("Applies to Map, Performance, Trends, Routes. Not applied to the Mode tab itself (that's the cross-mode comparison) or Coverage (agency-level, not mode-level).")


# The realtime job ingests new data every minute (see orchestrator/definitions.py);
# this fragment re-queries and redraws on its own timer without resetting the
# sidebar selections above or the browser scroll position.
@st.fragment(run_every="30s")
def render_dashboard(selected_state, selected_district, selected_mode):
    st.caption(f"Auto-refreshing every 30s — last updated {datetime.now().strftime('%H:%M:%S')}")

    mode_clause = "AND route_type_label = ?" if selected_mode != "All Modes" else ""
    mode_params = [selected_mode] if selected_mode != "All Modes" else []

    with get_db_connection() as conn:
        # --- Coverage banner (blueprint §2.2): surface RT dark spots up front so ---
        # --- they read as "no data", not silently as "0 delay / on time".      ---
        coverage_df = conn.execute("""
            SELECT agency_id, agency_name, scheduled_trip_count, observed_trip_count, rt_coverage_pct
            FROM mrt_rt_coverage_by_agency
        """).df()
        dark_agencies = coverage_df[
            (coverage_df["scheduled_trip_count"] > 0) & (coverage_df["observed_trip_count"] == 0)
        ]
        if len(dark_agencies):
            st.warning(
                f"{len(dark_agencies)} of {len(coverage_df)} agencies have scheduled trips but "
                "**no realtime signal** in the trailing 24h — their stops mean 'no data', not "
                "'on time'. See the Coverage tab for the full list."
            )

        tab_map, tab_performance, tab_mode, tab_routes, tab_trends, tab_disruptions, tab_coverage = st.tabs(
            ["Map", "Performance", "Mode", "Routes", "Trends", "Disruptions", "Coverage"]
        )

        # --- Map ---
        with tab_map:
            color_metric = st.radio(
                "Color by", ["avg_delay_minutes", "delayed_percentage"],
                format_func=lambda v: "Average delay" if v == "avg_delay_minutes" else "% delayed >5min",
                horizontal=True, key="map_color_metric",
            )
            # Queried live from int_trip_delays_enriched (not the pre-materialized
            # marts) so the mode filter applies here too.
            if selected_state == "All Germany":
                map_df = conn.execute(f"""
                    WITH stop_locations AS (
                        SELECT DISTINCT stop_id, municipality_id, stop_lat, stop_lon
                        FROM int_trip_delays_enriched
                        WHERE municipality_id IS NOT NULL {mode_clause}
                    ),
                    centroids AS (
                        SELECT municipality_id, AVG(stop_lat) AS lat, AVG(stop_lon) AS lon
                        FROM stop_locations GROUP BY 1
                    )
                    SELECT m.municipality_name AS label, c.lat, c.lon,
                           AVG(m.arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                           SUM(CASE WHEN m.is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
                           COUNT(*) AS total_observations
                    FROM int_trip_delays_enriched m
                    JOIN centroids c ON m.municipality_id = c.municipality_id
                    WHERE 1=1 {mode_clause}
                    GROUP BY 1, 2, 3
                """, mode_params + mode_params).df()
                st.caption("Municipality-level centroids for all of Germany. Select a state for stop-level detail.")
                point_radius = 300
                zoom = 5.3
            else:
                query = f"""
                    SELECT stop_name AS label, stop_lat AS lat, stop_lon AS lon,
                           AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                           SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage,
                           COUNT(*) AS total_observations
                    FROM int_trip_delays_enriched
                    WHERE state_name = ? AND stop_lat IS NOT NULL {mode_clause}
                """
                params = [selected_state] + mode_params
                if selected_district != "All Districts":
                    query += " AND district_name = ?"
                    params.append(selected_district)
                query += " GROUP BY 1, 2, 3"
                map_df = conn.execute(query, params).df()
                region_label = selected_district if selected_district != "All Districts" else selected_state
                st.caption(f"{len(map_df)} stops in {region_label}.")
                point_radius = 80
                zoom = 9 if selected_district != "All Districts" else 7.5

            if map_df.empty:
                st.info("No geolocated observations for this selection yet.")
            else:
                # Green -> red: avg delay clamped to 15min, % delayed clamped to 50%.
                clamp_max = 15 if color_metric == "avg_delay_minutes" else 50
                clamped = map_df[color_metric].clip(-5 if color_metric == "avg_delay_minutes" else 0, clamp_max)
                map_df["color_r"] = (clamped / clamp_max * 255).clip(0, 255)
                map_df["color_g"] = 255 - map_df["color_r"]

                layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=map_df,
                    get_position=["lon", "lat"],
                    get_radius=point_radius,
                    get_fill_color=["color_r", "color_g", 60, 180],
                    pickable=True,
                )
                view_state = pdk.ViewState(
                    latitude=float(map_df["lat"].mean()),
                    longitude=float(map_df["lon"].mean()),
                    zoom=zoom,
                )
                st.pydeck_chart(pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    tooltip={
                        "text": "{label}\nAvg delay: {avg_delay_minutes} min\n"
                                "% delayed: {delayed_percentage}\nObservations: {total_observations}"
                    },
                ))

        # --- Performance (state -> district -> municipality drill-down) ---
        with tab_performance:
            st.caption(
                "Average alone can mislead for high-volume areas — a large majority of "
                "on-time trips pulls it toward zero even when a real tail is badly delayed. "
                "Median and p90 (90% of trips are within this many minutes) show the shape "
                "instead of one number."
            )
            # All three levels queried live from int_trip_delays_enriched (not
            # the pre-materialized marts) so the mode filter applies uniformly.
            if selected_state == "All Germany":
                df_national = conn.execute(f"""
                    SELECT state_name, COUNT(*) AS total_observations,
                           AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                           MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
                           QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
                           SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
                    FROM int_trip_delays_enriched
                    WHERE state_name IS NOT NULL {mode_clause}
                    GROUP BY 1 ORDER BY delayed_percentage DESC
                """, mode_params).df()
                st.subheader("Country-Level Macro View: Delays by State")
                st.dataframe(df_national, width="stretch")
                if not df_national.empty:
                    st.bar_chart(df_national.set_index("state_name")["delayed_percentage"])
            elif selected_district == "All Districts":
                # Averaging per-municipality medians/percentages unweighted would let
                # a 1-observation municipality count the same as a 10,000-observation
                # one, so this is computed from raw rows, not re-aggregated marts.
                df_district = conn.execute(f"""
                    SELECT district_name, COUNT(*) AS total_observations,
                           AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                           MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
                           SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
                    FROM int_trip_delays_enriched
                    WHERE state_name = ? AND district_name IS NOT NULL {mode_clause}
                    GROUP BY 1 ORDER BY delayed_percentage DESC
                """, [selected_state] + mode_params).df()
                st.subheader(f"District-Level View: {selected_state}")
                st.dataframe(df_district, width="stretch")
                if not df_district.empty:
                    st.bar_chart(df_district.set_index("district_name")["delayed_percentage"])
            else:
                df_municipality = conn.execute(f"""
                    SELECT municipality_name, COUNT(*) AS total_observations,
                           AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                           MEDIAN(arrival_delay_sec) / 60.0 AS median_delay_minutes,
                           QUANTILE_CONT(arrival_delay_sec, 0.9) / 60.0 AS p90_delay_minutes,
                           SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS delayed_percentage
                    FROM int_trip_delays_enriched
                    WHERE district_name = ? {mode_clause}
                    GROUP BY 1 ORDER BY delayed_percentage DESC
                """, [selected_district] + mode_params).df()
                st.subheader(f"Village / Municipality Micro-View: {selected_district}")
                st.dataframe(df_municipality, width="stretch")

        # --- Mode: split by transport mode (bus/rail/tram/subway/ferry) ---
        with tab_mode:
            st.caption("National split — mode breakdown isn't filtered by the sidebar selection (medians don't combine validly across a per-state pre-aggregation).")
            mode_df = conn.execute("""
                SELECT route_type_label, total_observations, distinct_routes,
                       avg_delay_minutes, median_delay_minutes, p90_delay_minutes, delayed_percentage
                FROM mrt_performance_by_mode ORDER BY delayed_percentage DESC
            """).df()
            st.dataframe(mode_df, width="stretch")
            if not mode_df.empty:
                melted = mode_df.melt(
                    id_vars="route_type_label",
                    value_vars=["avg_delay_minutes", "median_delay_minutes", "p90_delay_minutes"],
                    var_name="metric", value_name="minutes",
                )
                fig_mode = px.bar(melted, x="route_type_label", y="minutes", color="metric",
                                   barmode="group", title="Delay by mode: average vs. median vs. p90")
                st.plotly_chart(fig_mode, width="stretch")
                fig_mode_pct = px.bar(mode_df, x="route_type_label", y="delayed_percentage",
                                       title="% of trips delayed >5min, by mode")
                st.plotly_chart(fig_mode_pct, width="stretch")

        # --- Routes: worst-performing individual routes (min. 20 observations) ---
        with tab_routes:
            st.caption("The underlying mart already floors at 20 observations per route so a single bad poll can't dominate; the slider below can only raise that floor further.")
            route_agencies = conn.execute(
                "SELECT DISTINCT agency_name FROM mrt_performance_by_route WHERE agency_name IS NOT NULL ORDER BY 1"
            ).df()["agency_name"].tolist()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                sort_by = st.selectbox(
                    "Sort by", ["delayed_percentage", "p90_delay_minutes", "avg_delay_minutes", "total_observations"],
                    key="routes_sort_by",
                )
            with col2:
                selected_agency = st.selectbox("Agency", ["All Agencies"] + route_agencies, key="routes_agency")
            with col3:
                min_obs = st.slider("Min. observations", 20, 500, 20, key="routes_min_obs")
            with col4:
                row_limit = st.slider("Rows to show", 10, 200, 50, key="routes_limit")

            routes_where = ["total_observations >= ?"]
            routes_params = [min_obs]
            if selected_mode != "All Modes":
                routes_where.append("route_type_label = ?")
                routes_params.append(selected_mode)
            if selected_agency != "All Agencies":
                routes_where.append("agency_name = ?")
                routes_params.append(selected_agency)

            routes_df = conn.execute(f"""
                SELECT route_short_name, agency_name, route_type_label, total_observations,
                       avg_delay_minutes, median_delay_minutes, p90_delay_minutes, delayed_percentage
                FROM mrt_performance_by_route
                WHERE {' AND '.join(routes_where)}
                ORDER BY {sort_by} DESC LIMIT {row_limit}
            """, routes_params).df()
            if routes_df.empty:
                st.info("No routes match this filter combination.")
            else:
                st.dataframe(routes_df, width="stretch")

        # --- Trends: delay over polling history for the current selection ---
        with tab_trends:
            granularity = st.selectbox("Bucket by", ["minute", "hour", "day"], key="trends_granularity")
            st.caption("Hour/day buckets will fill in as the realtime job accumulates more polling history — right now that's limited to how long ingestion has been running.")

            where_clause = "WHERE 1=1"
            params = []
            if selected_state != "All Germany":
                where_clause += " AND state_name = ?"
                params.append(selected_state)
                if selected_district != "All Districts":
                    where_clause += " AND district_name = ?"
                    params.append(selected_district)
            where_clause += f" {mode_clause}"
            params += mode_params

            trend_df = conn.execute(f"""
                SELECT date_trunc('{granularity}', ingested_at) AS bucket,
                       AVG(arrival_delay_sec) / 60.0 AS avg_delay_minutes,
                       COUNT(*) AS observations
                FROM int_trip_delays_enriched
                {where_clause}
                GROUP BY 1 ORDER BY 1
            """, params).df()

            if trend_df.empty:
                st.info("No polling history for this selection yet.")
            elif len(trend_df) == 1:
                st.info(
                    "Only one polling snapshot so far — a trend line needs the realtime job "
                    "(runs every minute) to accumulate more history."
                )
                st.dataframe(trend_df, width="stretch")
            else:
                fig = px.line(trend_df, x="bucket", y="avg_delay_minutes", markers=True,
                               title="Average delay over time")
                st.plotly_chart(fig, width="stretch")

            # Distribution, not just a point estimate — this is what actually shows
            # whether "average ~0" means "everyone's on time" or "early trips and
            # late trips cancel out." Binned in SQL (not pulled row-by-row into
            # pandas): "All Germany" can be millions of rows, this always returns
            # ~80.
            st.subheader("Delay Distribution")
            dist_df = conn.execute(f"""
                SELECT FLOOR(GREATEST(LEAST(arrival_delay_sec / 60.0, 60), -20)) AS bucket_start,
                       COUNT(*) AS observations
                FROM int_trip_delays_enriched
                {where_clause} AND arrival_delay_sec IS NOT NULL
                GROUP BY 1 ORDER BY 1
            """, params).df()
            if dist_df.empty:
                st.info("No delay observations for this selection yet.")
            else:
                total_obs = int(dist_df["observations"].sum())
                fig_hist = px.bar(
                    dist_df, x="bucket_start", y="observations",
                    title=f"Delay distribution ({total_obs:,} observations, clamped to [-20, 60] min)",
                    labels={"bucket_start": "Delay (minutes)", "observations": "Count"},
                )
                fig_hist.add_vline(x=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_hist, width="stretch")

        # --- Disruptions: GTFS-RT service alerts, national (not stop/route-linkable) ---
        with tab_disruptions:
            st.caption(
                "National — GTFS-RT ServiceAlerts never populate route_ids/agency_ids in this "
                "feed (0 of 1.5M rows observed), so alerts can't be linked to a specific route, "
                "agency, or the sidebar's spatial/mode filters."
            )
            st.warning(
                "Data quality note: this feed also (mis)uses the alerts mechanism for static "
                "vehicle-amenity tags (e.g. 'Niederflur' = low-floor, 'Klimaanlage' = has A/C) "
                "mixed in with genuine disruptions, and there's no reliable automatic way to tell "
                "them apart from text alone — length and keywords both fail (e.g. 'Streckensperrung' "
                "is a real 16-character closure notice; 'Linie RE7: Klimaanlage' is a 22-character "
                "amenity note). An unambiguous legal-attribution boilerplate message (~77% of all "
                "alert volume) is already excluded below; the rest is shown as-is — use search or "
                "the keyword filter to narrow toward genuine disruptions."
            )

            alerts_by_cause = conn.execute("SELECT * FROM mrt_alerts_by_cause").df()
            active_total = int(alerts_by_cause["currently_active"].sum())
            st.metric("Currently active alerts (attribution noise excluded)", f"{active_total:,}")
            if not alerts_by_cause.empty:
                fig_cause = px.bar(alerts_by_cause, x="cause", y="currently_active",
                                    title="Active alerts by cause")
                st.plotly_chart(fig_cause, width="stretch")

            active_alerts = conn.execute("""
                SELECT cause, alert_title, description_text, first_seen_at, last_seen_at
                FROM mrt_active_alerts ORDER BY first_seen_at DESC
            """).df()

            col1, col2 = st.columns(2)
            with col1:
                search = st.text_input("Search alert text", key="alerts_search")
            with col2:
                hide_amenities = st.checkbox(
                    "Try to hide vehicle/amenity tags (heuristic keyword match — imperfect, may miss some or exclude real disruptions that happen to mention these words)",
                    key="alerts_hide_amenities",
                )

            display_alerts = active_alerts
            if search:
                mask = (
                    display_alerts["alert_title"].str.contains(search, case=False, na=False)
                    | display_alerts["description_text"].str.contains(search, case=False, na=False)
                )
                display_alerts = display_alerts[mask]
            if hide_amenities:
                amenity_keywords = [
                    "niederflur", "hochflur", "rollstuhlgeeignet", "klimaanlage", "wlan",
                    "bordrestaurant", "steckdose", "toilette", "einstiegshilfe", "barrierefrei",
                    "gelenkbus", "solobus", "kleinbus", "ruhezone", "1. kl", "1.klasse", "1. klasse",
                ]
                pattern = "|".join(amenity_keywords)
                mask = ~(
                    display_alerts["alert_title"].str.contains(pattern, case=False, na=False, regex=True)
                    | display_alerts["description_text"].str.contains(pattern, case=False, na=False, regex=True)
                )
                display_alerts = display_alerts[mask]

            st.caption(f"{len(display_alerts)} of {len(active_alerts)} active alerts shown.")
            if display_alerts.empty:
                st.info("No alerts match this filter.")
            else:
                st.dataframe(display_alerts, width="stretch")

        # --- Coverage: which agencies actually have realtime data ---
        with tab_coverage:
            st.subheader("Realtime Coverage by Agency (trailing 24h)")
            st.caption(
                "0% coverage with scheduled trips > 0 means no realtime signal at all for that "
                "agency — its stops are missing data, not performing well. Agency-level only, "
                "not filtered by the Mode selector (one agency can run several modes)."
            )
            search = st.text_input("Search agency name", key="coverage_search")
            display_df = coverage_df
            if search:
                display_df = display_df[display_df["agency_name"].str.contains(search, case=False, na=False)]
            st.dataframe(
                display_df.sort_values("rt_coverage_pct", na_position="first"),
                width="stretch",
            )


render_dashboard(selected_state, selected_district, selected_mode)
