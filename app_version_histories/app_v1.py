# app.py
# Streamlit front-end for Neo4j Robot Selection DSS
# Adds:
#  1) Recommended robot highlight + Fit Score %
#  2) Adjustable weighting sliders (payload/reach/precision/axes)
#  3) What-if analysis sliders (relax reach/payload/precision)
#  4) Simple visualisations (bar chart + scatter payload vs reach)
#  5) CSV download

import os
from typing import Dict, Any, List
from decimal import Decimal, ROUND_DOWN


import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase


# -------------------------
# Config / Secrets
# -------------------------
load_dotenv()

# Reads NEO4J_USERNAME to match your setup.
# If you prefer NEO4J_USER, change the line accordingly (and your .env).
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

DEFAULT_URI = NEO4J_URI
DEFAULT_USER = NEO4J_USERNAME
DEFAULT_PASSWORD = NEO4J_PASSWORD

# -------------------------
# Helpers
# -------------------------
def fmt_fit_score(score: float, fully_suitable: bool) -> str:
    score = float(score)
    # Only allow 100.0% if fully suitable AND mathematically perfect
    if fully_suitable and abs(score - 100.0) < 1e-9:
        return "100.0%"
    # Otherwise cap at 99.9%
    score = min(score, 99.9)
    return f"{score:.1f}%"

def render_robot_card(row, rank_idx: int):
    fully = bool(row.get("fullySuitable", False))

    score = float(row.get("fitScore", 0.0)) if "fitScore" in row else (
        100.0 * (1.0 - float(row.get("distanceScore", 0.0))))

    score_txt = fmt_fit_score(score, fully)

    # subtle colours (Option 1)
    if fully:
        bg = "rgba(46,125,50,0.06)"
        border = "rgba(46,125,50,0.6)"
        badge = "✅ Fully suitable"
    elif score >= 80:
        bg = "rgba(245,124,0,0.06)"
        border = "rgba(245,124,0,0.6)"
        badge = "🟡 Near match"
    else:
        bg = "rgba(198,40,40,0.05)"
        border = "rgba(198,40,40,0.55)"
        badge = "🔴 Off spec"

    robot = row.get("robot", "")
    rtype = row.get("robotType", "")
    manu = row.get("manufacturer", "")
    notes = row.get("notes", "")

    # These are the formatted strings you already return in Cypher:
    payload = row.get("payload", "")
    reach = row.get("reach", "")
    rep = row.get("repeatability", "")
    axes = row.get("axes", "")

    medal = "🥇" if rank_idx == 0 else ("🥈" if rank_idx == 1 else "🥉")

    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-left: 6px solid {border};
            border-radius: 14px;
            padding: 14px 16px;
            margin: 10px 0;
        ">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
            <div>
              <div style="font-size:18px; font-weight:700;">{medal} {robot}</div>
              <div style="opacity:0.85; font-size:13px;">{badge} · {rtype} · {manu}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:12px; opacity:0.8;">Fit score</div>
              <div style="font-size:22px; font-weight:800;">{score_txt}</div>
            </div>
          </div>

          <div style="margin-top:10px; display:grid; grid-template-columns: 120px 1fr; row-gap:6px; column-gap:10px; font-size:13px;">
            <div style="opacity:0.85;">Payload</div><div>{payload}</div>
            <div style="opacity:0.85;">Reach</div><div>{reach}</div>
            <div style="opacity:0.85;">Repeatability</div><div>{rep}</div>
            <div style="opacity:0.85;">Axes</div><div>{axes}</div>
          </div>

          <div style="margin-top:10px; font-size:12px; opacity:0.85;">
            <b>Notes:</b> {notes}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# -------------------------
# Cypher Queries
# -------------------------
Q_LIST_APPLICATIONS = """
MATCH (a:ApplicationRequirement)
RETURN a.applicationId AS applicationId, a.applicationType AS applicationType
ORDER BY applicationId;
"""

# Note:
# - Uses relax factors to widen ranges / relax precision:
#     relaxReachPct=10 means:
#        reachMinRelax = reachMin*(1-0.10), reachMaxRelax = reachMax*(1+0.10)
#     relaxPayloadPct similarly.
#     relaxPrecisionPct=10 means:
#        repeatabilityAllowed = repReq*(1+0.10)
# - Weighted distanceScore uses wPayload/wReach/wPrecision/wAxes (should sum to 1).
Q_RANK_ROBOTS_FOR_APP = """
MATCH (a:ApplicationRequirement {applicationId: $appId})
MATCH (r:Robot)

WITH r, a,
     $relaxReachPct / 100.0     AS relaxReach,
     $relaxPayloadPct / 100.0   AS relaxPayload,
     $relaxPrecisionPct / 100.0 AS relaxPrecision,

     $wPayload   AS wPayload,
     $wReach     AS wReach,
     $wPrecision AS wPrecision,
     $wAxes      AS wAxes

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     // relaxed requirement bounds
     (a.payloadMinKg * (1 - relaxPayload)) AS payloadMinR,
     (a.payloadMaxKg * (1 + relaxPayload)) AS payloadMaxR,

     (a.reachMinMm * (1 - relaxReach)) AS reachMinR,
     (a.reachMaxMm * (1 + relaxReach)) AS reachMaxR,

     (a.repeatabilityRequiredMm * (1 + relaxPrecision)) AS repReqR,

     a.axesMin AS axesMinR

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,

     // pass/fail checks under relaxed bounds
     (r.payloadKg >= payloadMinR AND r.payloadKg <= payloadMaxR) AS passPayload,
     (r.reachMm   >= reachMinR   AND r.reachMm   <= reachMaxR)   AS passReach,
     (r.repeatabilityMm <= repReqR)                              AS passPrecision,
     (r.axis >= axesMinR)                                        AS passAxes,

     // gaps (0 means meets requirement; otherwise relative shortfall)
     CASE
       WHEN r.payloadKg < payloadMinR THEN (payloadMinR - r.payloadKg) / payloadMinR
       WHEN r.payloadKg > payloadMaxR THEN (r.payloadKg - payloadMaxR) / payloadMaxR
       ELSE 0
     END AS payloadGap,

     CASE
       WHEN r.reachMm < reachMinR THEN (reachMinR - r.reachMm) / reachMinR
       WHEN r.reachMm > reachMaxR THEN (r.reachMm - reachMaxR) / reachMaxR
       ELSE 0
     END AS reachGap,

     CASE
       WHEN r.repeatabilityMm > repReqR THEN (r.repeatabilityMm - repReqR) / repReqR
       ELSE 0
     END AS precisionGap,

     CASE
       WHEN r.axis < axesMinR THEN (axesMinR - r.axis) * 1.0 / axesMinR
       ELSE 0
     END AS axesGap

WITH r, a, payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     passPayload, passReach, passPrecision, passAxes,
     payloadGap, reachGap, precisionGap, axesGap,

     // IMPORTANT: keep raw score full precision (do NOT round here)
     (wPayload*payloadGap + wReach*reachGap + wPrecision*precisionGap + wAxes*axesGap) AS distanceScoreRaw,

     (passPayload AND passReach AND passPrecision AND passAxes) AS fullySuitable,
     [
       CASE WHEN NOT passPayload THEN "Payload out of range" END,
       CASE WHEN NOT passReach THEN "Reach out of range" END,
       CASE WHEN NOT passPrecision THEN "Repeatability not sufficient" END,
       CASE WHEN NOT passAxes THEN "Insufficient axes" END
     ] AS rawReasons

WITH r, a, payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     fullySuitable, distanceScoreRaw,
     payloadGap, reachGap, precisionGap, axesGap,
     [x IN rawReasons WHERE x IS NOT NULL] AS reasons

RETURN
  a.applicationId AS app,
  a.applicationType AS applicationType,

  r.robotModel AS robot,
  r.type AS robotType,
  r.manufacturer AS manufacturer,
  fullySuitable,

  // numeric fields (useful for plotting)
  r.payloadKg AS payloadKg,
  r.reachMm AS reachMm,
  r.repeatabilityMm AS repeatabilityMm,
  r.axis AS axes,

  // show relaxed requirements as numbers too (handy)
  payloadMinR AS payloadMinReq,
  payloadMaxR AS payloadMaxReq,
  reachMinR   AS reachMinReq,
  reachMaxR   AS reachMaxReq,
  repReqR     AS repeatabilityReq,
  axesMinR    AS axesMinReq,

  // formatted requirement comparisons (RELAXED requirements shown)
  toString(r.payloadKg) + " kg (req " + toString(round(payloadMinR*100)/100.0) + "–" + toString(round(payloadMaxR*100)/100.0) + ")" AS payload,
  toString(r.reachMm) + " mm (req " + toString(round(reachMinR*1.0)/1.0) + "–" + toString(round(reachMaxR*1.0)/1.0) + ")" AS reach,
  toString(r.repeatabilityMm) + " mm (req ≤ " + toString(round(repReqR*1000)/1000.0) + ")" AS repeatability,
  toString(r.axis) + " (req ≥ " + toString(axesMinR) + ")" AS axesReq,

  // human-readable notes
  CASE
    WHEN fullySuitable THEN "Meets all requirements"
    ELSE reduce(s="", rr IN reasons | CASE WHEN s="" THEN rr ELSE s + "; " + rr END)
  END AS notes,

  // DISPLAY ONLY: rounded score (4 dp so tiny misses still show)
  round(distanceScoreRaw*10000)/10000 AS distanceScore,

  // Fit score from RAW (never from rounded)
  round((1 - distanceScoreRaw) * 1000)/10.0 AS fitScore,

  // Optional: show gaps so you can sanity check why something isn't perfect
  round(payloadGap*100000)/100000 AS payloadGap,
  round(reachGap*100000)/100000 AS reachGap,
  round(precisionGap*100000)/100000 AS precisionGap,
  round(axesGap*100000)/100000 AS axesGap

ORDER BY distanceScoreRaw ASC, fullySuitable DESC, robot
LIMIT $limit;
"""
# -------------------------
# Neo4j helper
# -------------------------
def run_query(driver, query: str, params: Dict[str, Any] | None = None, database: str | None = None) -> pd.DataFrame:
    with driver.session(database=database) as session:
        result = session.run(query, params or {})
        rows: List[Dict[str, Any]] = [r.data() for r in result]
    return pd.DataFrame(rows)


# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Robot Selection DSS (Neo4j)", layout="wide")
st.title("Robot Selection DSS (Neo4j Knowledge Graph)")

with st.sidebar:
    st.header("Connection")

    have_env_creds = bool(DEFAULT_URI and DEFAULT_USER and DEFAULT_PASSWORD)

    if have_env_creds:
        st.success("Using credentials from environment (.env).")
        uri = DEFAULT_URI
        user = DEFAULT_USER
        password = DEFAULT_PASSWORD
        connect_btn = False
    else:
        st.warning("No credentials found in environment. Enter them below.")
        uri = st.text_input("Neo4j URI", value=DEFAULT_URI, placeholder="neo4j+s://xxxx.databases.neo4j.io")
        user = st.text_input("Username", value=DEFAULT_USER or "neo4j")
        password = st.text_input("Password", value=DEFAULT_PASSWORD, type="password")
        connect_btn = st.button("Connect", type="primary")

    st.divider()
    st.header("Ranking controls")

    limit = st.slider("Max results", min_value=10, max_value=200, value=50, step=10)

    st.subheader("Weighting")

    use_weighting = st.toggle(
        "Enable custom weighting",
        value=False,
        help="Turn on to prioritise certain criteria over others"
    )

    if use_weighting:

        st.caption("Adjust importance of each criterion")

        w_payload = st.slider(
            "Payload importance",
            0.0, 1.0, 0.30, 0.05
        )

        w_reach = st.slider(
            "Reach importance",
            0.0, 1.0, 0.25, 0.05
        )

        w_precision = st.slider(
            "Precision importance",
            0.0, 1.0, 0.35, 0.05
        )

        w_axes = st.slider(
            "Axes importance",
            0.0, 1.0, 0.10, 0.05
        )

    else:

        # Equal weighting
        w_payload = 0.25
        w_reach = 0.25
        w_precision = 0.25
        w_axes = 0.25

    st.subheader("What-if relaxation (%)")
    relax_payload_pct = st.slider("Relax payload range", 0, 50, 0, 1)
    relax_reach_pct = st.slider("Relax reach range", 0, 50, 0, 1)
    relax_precision_pct = st.slider("Relax repeatability requirement", 0, 50, 0, 1)

# Initialise session state
if "driver" not in st.session_state:
    st.session_state.driver = None
if "conn_error" not in st.session_state:
    st.session_state.conn_error = None

# Auto-connect
if st.session_state.driver is None and have_env_creds:
    try:
        st.session_state.driver = GraphDatabase.driver(uri, auth=(user, password))
        _ = run_query(st.session_state.driver, "RETURN 1 AS ok;", database=NEO4J_DATABASE)
        st.session_state.conn_error = None
    except Exception as e:
        st.session_state.driver = None
        st.session_state.conn_error = str(e)

# Manual connect
if st.session_state.driver is None and (not have_env_creds) and connect_btn:
    if not uri or not user or not password:
        st.session_state.conn_error = "Please provide URI, username, and password."
    else:
        try:
            st.session_state.driver = GraphDatabase.driver(uri, auth=(user, password))
            _ = run_query(st.session_state.driver, "RETURN 1 AS ok;", database=NEO4J_DATABASE)
            st.session_state.conn_error = None
        except Exception as e:
            st.session_state.driver = None
            st.session_state.conn_error = str(e)

# Show connection status
if st.session_state.driver is None:
    if st.session_state.conn_error:
        st.error(f"Not connected: {st.session_state.conn_error}")
    else:
        st.info("Enter your Neo4j Aura URI + credentials in the sidebar, then click **Connect**.")
    st.stop()

st.success("Connected.")
driver = st.session_state.driver

# Show weighting status
if use_weighting:
    st.info("Custom weighting enabled")
else:
    st.info("Equal weighting applied")

# Load applications
apps_df = run_query(driver, Q_LIST_APPLICATIONS, database=NEO4J_DATABASE)
if apps_df.empty:
    st.error("No ApplicationRequirement nodes found. Import data first.")
    st.stop()

apps_df["applicationType"] = apps_df["applicationType"].fillna("")
apps_df["label"] = apps_df["applicationId"] + " — " + apps_df["applicationType"]
selected_label = st.selectbox("Select application", apps_df["label"].tolist(), index=0)
selected_app_id = selected_label.split(" — ")[0].strip()

# Normalise weights (so they always sum to 1)
w_sum = float(w_payload + w_reach + w_precision + w_axes)
if w_sum <= 0:
    # fallback to equal weights if user zeros everything
    w_payload_n = w_reach_n = w_precision_n = w_axes_n = 0.25
else:
    w_payload_n = w_payload / w_sum
    w_reach_n = w_reach / w_sum
    w_precision_n = w_precision / w_sum
    w_axes_n = w_axes / w_sum

# Run ranking query
params = {
    "appId": selected_app_id,
    "limit": int(limit),
    "wPayload": float(w_payload_n),
    "wReach": float(w_reach_n),
    "wPrecision": float(w_precision_n),
    "wAxes": float(w_axes_n),
    "relaxPayloadPct": int(relax_payload_pct),
    "relaxReachPct": int(relax_reach_pct),
    "relaxPrecisionPct": int(relax_precision_pct),
}
rank_df = run_query(driver, Q_RANK_ROBOTS_FOR_APP, params=params, database=NEO4J_DATABASE)

# Summary cards
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Application", selected_app_id)
with col2:
    st.metric("Robots shown", int(len(rank_df)))
with col3:
    fully_count = int(rank_df["fullySuitable"].sum()) if (not rank_df.empty and "fullySuitable" in rank_df.columns) else 0
    st.metric("Fully suitable in list", fully_count)
with col4:
    st.metric("Relaxation", f"P{relax_payload_pct}% / R{relax_reach_pct}% / Rep{relax_precision_pct}%")

# Subtle professional recommendation cards
st.subheader("Top 3 Recommended Robots")

top3 = rank_df.head(3).copy()
for i, (_, row) in enumerate(top3.iterrows()):
    render_robot_card(row, i)

#Shortlist table
st.subheader("Ranked robot shortlist")

if rank_df.empty:
    st.warning("No robots returned. Try increasing the limit or check your data import.")
    st.stop()

# Table
preferred_cols = [
    "distanceScore", "fullySuitable",
    "robot", "robotType", "manufacturer",
    "payload", "reach", "repeatability", "axesReq",
    "notes"
]
cols = [c for c in preferred_cols if c in rank_df.columns] + [c for c in rank_df.columns if c not in preferred_cols]
st.dataframe(rank_df[cols], use_container_width=True, hide_index=True)

# Download CSV
csv_bytes = rank_df[cols].to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_bytes,
    file_name=f"robot_ranking_{selected_app_id}.csv",
    mime="text/csv",
)

# Visualisations
st.divider()
st.subheader("Visualisations")

viz_col1, viz_col2 = st.columns(2)

with viz_col1:
    st.caption("Distance score (lower is better) — top results")
    # Use top N for readability
    top_n = min(25, len(rank_df))
    chart_df = rank_df.head(top_n).copy()
    # index by robot for chart labels
    if "robot" in chart_df.columns and "distanceScore" in chart_df.columns:
        chart_df = chart_df.set_index("robot")[["distanceScore"]]
        st.bar_chart(chart_df)

with viz_col2:
    st.caption("Capability scatter: Reach vs Payload (top results)")
    # Keep only numeric columns for charting
    if {"reachMm", "payloadKg"}.issubset(rank_df.columns):
        scatter_df = rank_df.head(min(80, len(rank_df)))[["robot", "reachMm", "payloadKg", "fullySuitable"]].copy()
        # Streamlit scatter_chart needs numeric columns; we can still show a simple one
        st.scatter_chart(scatter_df, x="reachMm", y="payloadKg")

st.divider()
st.caption(
    "Tip: Weight sliders demonstrate decision-maker preferences; relaxation sliders demonstrate what-if scenario analysis. "
)