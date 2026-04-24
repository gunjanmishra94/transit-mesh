import os
from datetime import datetime

import duckdb
import plotly.express as px
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="German Transit Intelligence", layout="wide")

DB_PATH = os.getenv("DUCKDB_PATH", "duckdb_data/transit.duckdb")


@st.cache_resource
def get_db_connection():
    return duckdb.connect(DB_PATH, read_only=True)


try:
    conn = get_db_connection()
    conn.execute("SELECT 1 FROM mrt_performance_national LIMIT 1")
except Exception:
    st.error(
        "DuckDB file not found or the pipeline hasn't run yet. "
        "Run ingestion + `dbt build` first (see README)."
    )
    st.stop()

st.title("🇩🇪 Nationwide Transit Intelligence Platform")
st.markdown("Real-time telemetry, delay propagation, and spatial analytics from country to village level.")

# --- Sidebar drill-down, shared across tabs ---
st.sidebar.header("Spatial Drill-Down")
states = [r[0] for r in conn.execute(
    "SELECT DISTINCT state_name FROM mrt_performance_by_municipality WHERE state_name IS NOT NULL ORDER BY 1"
).fetchall()]
selected_state = st.sidebar.selectbox("Bundesland", ["All Germany"] + states)

selected_district = "All Districts"
if selected_state != "All Germany":
    districts = [r[0] for r in conn.execute(
        "SELECT DISTINCT district_name FROM mrt_performance_by_municipality "
        "WHERE state_name = ? AND district_name IS NOT NULL ORDER BY 1",
        [selected_state],
    ).fetchall()]
    selected_district = st.sidebar.selectbox("Landkreis", ["All Districts"] + districts)


# The realtime job ingests new data every minute (see orchestrator/definitions.py);
# this fragment re-queries and redraws on its own timer without resetting the
# sidebar selections above or the browser scroll position.
@st.fragment(run_every="30s")
def render_dashboard(selected_state, selected_district):
    st.caption(f"Auto-refreshing every 30s — last updated {datetime.now().strftime('%H:%M:%S')}")

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

    tab_map, tab_performance, tab_trends, tab_coverage = st.tabs(["Map", "Performance", "Trends", "Coverage"])

    # --- Map ---
    with tab_map:
        if selected_state == "All Germany":
            map_df = conn.execute("""
                SELECT municipality_name AS label, centroid_lat AS lat, centroid_lon AS lon,
                       avg_delay_minutes, total_observations
                FROM mrt_performance_by_municipality
                WHERE centroid_lat IS NOT NULL
            """).df()
            st.caption("Municipality-level centroids for all of Germany. Select a state for stop-level detail.")
            point_radius = 300
            zoom = 5.3
        else:
            query = """
                SELECT stop_name AS label, stop_lat AS lat, stop_lon AS lon,
                       avg_delay_minutes, total_observations
                FROM mrt_performance_by_stop
                WHERE state_name = ? AND stop_lat IS NOT NULL
            """
            params = [selected_state]
            if selected_district != "All Districts":
                query += " AND district_name = ?"
                params.append(selected_district)
            map_df = conn.execute(query, params).df()
            region_label = selected_district if selected_district != "All Districts" else selected_state
            st.caption(f"{len(map_df)} stops in {region_label}.")
            point_radius = 80
            zoom = 9 if selected_district != "All Districts" else 7.5

        if map_df.empty:
            st.info("No geolocated observations for this selection yet.")
        else:
            # Green -> red as delay approaches/exceeds 15 minutes.
            clamped = map_df["avg_delay_minutes"].clip(-5, 15)
            map_df["color_r"] = (clamped / 15 * 255).clip(0, 255)
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
                tooltip={"text": "{label}\nAvg delay: {avg_delay_minutes} min\nObservations: {total_observations}"},
            ))

    # --- Performance (state -> district -> municipality drill-down) ---
    with tab_performance:
        if selected_state == "All Germany":
            df_national = conn.execute("""
                SELECT state_name, total_observations, avg_delay_minutes, delayed_percentage
                FROM mrt_performance_national ORDER BY avg_delay_minutes DESC
            """).df()
            st.subheader("Country-Level Macro View: Average Delays by State")
            st.dataframe(df_national, width="stretch")
            if not df_national.empty:
                st.bar_chart(df_national.set_index("state_name")["avg_delay_minutes"])
        elif selected_district == "All Districts":
            df_district = conn.execute("""
                SELECT district_name, SUM(total_observations) AS total_observations,
                       AVG(avg_delay_minutes) AS avg_delay_minutes
                FROM mrt_performance_by_municipality
                WHERE state_name = ? AND district_name IS NOT NULL
                GROUP BY 1 ORDER BY avg_delay_minutes DESC
            """, [selected_state]).df()
            st.subheader(f"District-Level View: {selected_state}")
            st.dataframe(df_district, width="stretch")
            if not df_district.empty:
                st.bar_chart(df_district.set_index("district_name")["avg_delay_minutes"])
        else:
            df_municipality = conn.execute("""
                SELECT municipality_name, total_observations, avg_delay_minutes, delayed_percentage
                FROM mrt_performance_by_municipality
                WHERE district_name = ? ORDER BY avg_delay_minutes DESC
            """, [selected_district]).df()
            st.subheader(f"Village / Municipality Micro-View: {selected_district}")
            st.dataframe(df_municipality, width="stretch")

    # --- Trends: delay over polling history for the current selection ---
    with tab_trends:
        where_clause = "WHERE 1=1"
        params = []
        if selected_state != "All Germany":
            where_clause += " AND state_name = ?"
            params.append(selected_state)
            if selected_district != "All Districts":
                where_clause += " AND district_name = ?"
                params.append(selected_district)

        trend_df = conn.execute(f"""
            SELECT date_trunc('minute', ingested_at) AS bucket,
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

    # --- Coverage: which agencies actually have realtime data ---
    with tab_coverage:
        st.subheader("Realtime Coverage by Agency (trailing 24h)")
        st.caption(
            "0% coverage with scheduled trips > 0 means no realtime signal at all for that "
            "agency — its stops are missing data, not performing well."
        )
        st.dataframe(
            coverage_df.sort_values("rt_coverage_pct", na_position="first"),
            width="stretch",
        )


render_dashboard(selected_state, selected_district)
