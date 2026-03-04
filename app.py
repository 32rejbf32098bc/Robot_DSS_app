# app.py
# Streamlit front-end for Neo4j Robot Selection DSS (split into modules)

import os
import math
from typing import Dict

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from ui_css import inject_css
from db import run_query, ensure_driver
from queries import Q_LIST_APPLICATIONS, Q_GET_APPLICATION_DETAILS, Q_RANK_ROBOTS_FOR_APP
from components import render_application_box, render_robot_card
from charts import _build_radar_for_topN

# -------------------------
# Config / Secrets
# -------------------------
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

DEFAULT_URI = NEO4J_URI
DEFAULT_USER = NEO4J_USERNAME
DEFAULT_PASSWORD = NEO4J_PASSWORD


def _weights_all_equal(w_norm: Dict[str, float], eps: float = 1e-9) -> bool:
    """Return True if all weights are (approximately) identical."""
    if not w_norm:
        return True
    vals = list(w_norm.values())
    return all(abs(v - vals[0]) < eps for v in vals)


def _safe_float(x, default: float = 1.0) -> float:
    """Float conversion that guards against None/NaN/Inf."""
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Robot Selection DSS (Neo4j)", layout="wide")
inject_css()

# session state
st.session_state.setdefault("driver", None)
st.session_state.setdefault("conn_error", None)

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.header("Connection")

    have_env_creds = bool(DEFAULT_URI and DEFAULT_USER and DEFAULT_PASSWORD)

    if have_env_creds:
        st.success("Using credentials from environment (.env).")
        uri = DEFAULT_URI
        user = DEFAULT_USER
        password = DEFAULT_PASSWORD
    else:
        st.warning("No credentials found in environment. Enter them below.")
        uri = st.text_input(
            "Neo4j URI",
            value=DEFAULT_URI,
            placeholder="neo4j+s://xxxx.databases.neo4j.io",
        )
        user = st.text_input("Username", value=DEFAULT_USER or "neo4j")
        password = st.text_input("Password", value=DEFAULT_PASSWORD, type="password")

    st.divider()
    st.header("Ranking controls")

    limit = st.slider("Max results", min_value=10, max_value=200, value=50, step=10)

    # -------------------------
    # Hard constraints
    # -------------------------
    st.subheader("Hard constraints", help="Exclude robots that don't meet these requirements.")

    HARD_KEYS = [
        "hard_payload",
        "hard_reach",
        "hard_precision",
        "hard_axes",
        "hard_budget",
        "hard_cycle",
        "hard_ip",
        "hard_cleanroom",
        "hard_esd",
        "hard_force",
        "hard_type",
    ]
    for k in HARD_KEYS:
        st.session_state.setdefault(k, False)
    st.session_state.setdefault("hard_master", False)

    def _set_all_hard(val: bool):
        for k in HARD_KEYS:
            st.session_state[k] = val

    def _any_hard_diff_from_master(master_val: bool) -> bool:
        return any(st.session_state.get(k, master_val) != master_val for k in HARD_KEYS)

    st.checkbox(
        "Apply all hard constraints",
        value=st.session_state.hard_master,
        key="hard_master",
        on_change=lambda: _set_all_hard(st.session_state.hard_master),
        help="Tick to enforce all constraints. Change any individual toggle to disable this master checkbox automatically.",
    )

    with st.expander("constraints", expanded=False):
        st.toggle("Payload", key="hard_payload")
        st.toggle("Reach", key="hard_reach")
        st.toggle("Repeatability", key="hard_precision")
        st.toggle("Axes", key="hard_axes")

        st.toggle("Budget", key="hard_budget")
        st.toggle("Cycle time", key="hard_cycle")
        st.toggle("IP rating", key="hard_ip")

        st.toggle("Cleanroom (if required)", key="hard_cleanroom")
        st.toggle("ESD (if required)", key="hard_esd")
        st.toggle("Force sensing (if required)", key="hard_force")

        st.toggle("Robot type", key="hard_type")

    # Always keep master truthful even when expander is collapsed
    if st.session_state.hard_master and _any_hard_diff_from_master(True):
        st.session_state.hard_master = False

    # -------------------------
    # Weighting (ALL adjustable; start equal) — now in a dropdown/expander
    # -------------------------
    st.subheader("Weighting")

    WEIGHT_KEYS = [
        ("Payload", "w_payload", 0.0, 1.0),
        ("Reach", "w_reach", 0.0, 1.0),
        ("Precision", "w_precision", 0.0, 1.0),
        ("Axes", "w_axes", 0.0, 1.0),
        ("Budget", "w_budget", 0.0, 1.0),
        ("Cycle", "w_cycle", 0.0, 1.0),
        ("IP", "w_ip", 0.0, 1.0),
        ("Cleanroom", "w_cleanroom", 0.0, 1.0),
        ("ESD", "w_esd", 0.0, 1.0),
        ("Force", "w_force", 0.0, 1.0),
        ("Type", "w_type", 0.0, 1.0),
    ]
    for _, key, _, _ in WEIGHT_KEYS:
        st.session_state.setdefault(key, 1.0)

    with st.expander("Custom weights", expanded=False):
        if st.button("Reset"):
            for _, key, _, _ in WEIGHT_KEYS:
                st.session_state[key] = 1.0
            st.rerun()

        for label, key, lo, hi in WEIGHT_KEYS:
            st.slider(label, lo, hi, step=0.01, key=key)

    # Normalise weights for query params (kept OUTSIDE expander so it always runs)
    w_raw = {
        "w_payload": _safe_float(st.session_state.get("w_payload", 1.0), 1.0),
        "w_reach": _safe_float(st.session_state.get("w_reach", 1.0), 1.0),
        "w_precision": _safe_float(st.session_state.get("w_precision", 1.0), 1.0),
        "w_axes": _safe_float(st.session_state.get("w_axes", 1.0), 1.0),
        "w_budget": _safe_float(st.session_state.get("w_budget", 1.0), 1.0),
        "w_cycle": _safe_float(st.session_state.get("w_cycle", 1.0), 1.0),
        "w_ip": _safe_float(st.session_state.get("w_ip", 1.0), 1.0),
        "w_cleanroom": _safe_float(st.session_state.get("w_cleanroom", 1.0), 1.0),
        "w_esd": _safe_float(st.session_state.get("w_esd", 1.0), 1.0),
        "w_force": _safe_float(st.session_state.get("w_force", 1.0), 1.0),
        "w_type": _safe_float(st.session_state.get("w_type", 1.0), 1.0),
    }
    w_sum = sum(w_raw.values())
    if w_sum <= 0:
        w_norm = {k: 1.0 / len(w_raw) for k in w_raw}
    else:
        w_norm = {k: v / w_sum for k, v in w_raw.items()}

    w_payload_n = w_norm["w_payload"]
    w_reach_n = w_norm["w_reach"]
    w_precision_n = w_norm["w_precision"]
    w_axes_n = w_norm["w_axes"]
    w_budget_n = w_norm["w_budget"]
    w_cycle_n = w_norm["w_cycle"]
    w_ip_n = w_norm["w_ip"]
    w_cleanroom_n = w_norm["w_cleanroom"]
    w_esd_n = w_norm["w_esd"]
    w_force_n = w_norm["w_force"]
    w_type_n = w_norm["w_type"]

    # -------------------------
    # Overspec penalty
    # -------------------------
    st.subheader("Overspec penalty")
    overspec_penalty = st.slider(
        "Penalty for overspec",
        min_value=0.0,
        max_value=0.50,
        value=0.15,
        step=0.01,
        help="Applies only when robot exceeds the application MAX range (still suitable, but slightly penalised).",
    )

    # -------------------------
    # What-if relaxation
    # -------------------------
    st.subheader("What-if relaxation")
    use_relaxation = st.toggle(
        "Enable relaxation",
        value=False,
        help="When off, all relaxation values are forced to 0%.",
    )

    if use_relaxation:
        relax_payload_pct = st.slider("Relax payload range", 0, 50, 0, 1)
        relax_reach_pct = st.slider("Relax reach range", 0, 50, 0, 1)
        relax_precision_pct = st.slider("Relax repeatability requirement", 0, 50, 0, 1)
    else:
        relax_payload_pct = 0
        relax_reach_pct = 0
        relax_precision_pct = 0

# -------------------------
# Connect
# -------------------------
driver = ensure_driver(
    current_driver=st.session_state.driver,
    uri=uri,
    user=user,
    password=password,
    database=NEO4J_DATABASE,
    conn_error_key="conn_error",
    driver_key="driver",
)

if driver is None:
    if st.session_state.conn_error:
        st.error(f"Not connected: {st.session_state.conn_error}")
    else:
        st.error("Not connected: missing credentials.")
    st.stop()

# -------------------------
# Load applications
# -------------------------
apps_df = run_query(driver, Q_LIST_APPLICATIONS, database=NEO4J_DATABASE)
if apps_df.empty or "applicationId" not in apps_df.columns:
    st.error("No applications found (or missing applicationId). Check your Neo4j data/import.")
    st.stop()

apps_df["applicationType"] = apps_df.get("applicationType", pd.Series(dtype=str)).fillna("")
app_ids = apps_df["applicationId"].tolist()

# Header row
col_title, col_status, col_select = st.columns([12, 8, 3], vertical_alignment="center")
with col_title:
    st.markdown("<h1 style='margin-bottom:0px;'>Robot Selection</h1>", unsafe_allow_html=True)

with col_status:
    weight_txt = "Equal" if _weights_all_equal(w_norm) else "Custom"
    st.markdown(
        f"""
        <div style="display:flex; justify-content:flex-end; gap:10px; align-items:center; margin-top:10px;">
          <span style="
            padding:4px 10px;
            border-radius:999px;
            font-size:12px;
            font-weight:600;
            background: rgba(46,125,50,0.10);
            color: rgba(46,125,50,1);
            border: 1px solid rgba(46,125,50,0.25);
          ">Connected</span>

          <span style="
            padding:4px 10px;
            border-radius:999px;
            font-size:12px;
            font-weight:600;
            background: rgba(30,58,138,0.08);
            color: rgba(160,190,255,1);
            border: 1px solid rgba(30,58,138,0.22);
          ">Weighting: {weight_txt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_select:
    selected_app_id = st.selectbox("Application", app_ids, label_visibility="collapsed")

# -------------------------
# Application details
# -------------------------
app_details_df = run_query(
    driver,
    Q_GET_APPLICATION_DETAILS,
    {"appId": selected_app_id},
    database=NEO4J_DATABASE,
)

if app_details_df.empty:
    st.error("No application details found for selected application ID.")
    st.stop()

app_row = app_details_df.iloc[0].to_dict()
render_application_box(app_row)

# -------------------------
# Rank query params
# -------------------------
params = {
    "appId": selected_app_id,
    "limit": int(limit),
    "wPayload": float(w_payload_n),
    "wReach": float(w_reach_n),
    "wPrecision": float(w_precision_n),
    "wAxes": float(w_axes_n),
    "wBudget": float(w_budget_n),
    "wCycle": float(w_cycle_n),
    "wIP": float(w_ip_n),
    "wCleanroom": float(w_cleanroom_n),
    "wESD": float(w_esd_n),
    "wForce": float(w_force_n),
    "wType": float(w_type_n),
    "relaxPayloadPct": int(relax_payload_pct),
    "relaxReachPct": int(relax_reach_pct),
    "relaxPrecisionPct": int(relax_precision_pct),
    "hardPayload": bool(st.session_state.hard_payload),
    "hardReach": bool(st.session_state.hard_reach),
    "hardPrecision": bool(st.session_state.hard_precision),
    "hardAxes": bool(st.session_state.hard_axes),
    "hardBudget": bool(st.session_state.hard_budget),
    "hardCycle": bool(st.session_state.hard_cycle),
    "hardIP": bool(st.session_state.hard_ip),
    "hardCleanroom": bool(st.session_state.hard_cleanroom),
    "hardESD": bool(st.session_state.hard_esd),
    "hardForce": bool(st.session_state.hard_force),
    "hardType": bool(st.session_state.hard_type),
    "wOverspec": float(overspec_penalty),
}

rank_df = run_query(driver, Q_RANK_ROBOTS_FOR_APP, params=params, database=NEO4J_DATABASE)
if rank_df.empty:
    st.warning("No robots returned. Try increasing the limit or check your imported data.")
    st.stop()

# -------------------------
# Summary cards (defensive against nulls/missing cols)
# -------------------------
fully = (
    rank_df["fullySuitable"].fillna(False).astype(bool)
    if "fullySuitable" in rank_df.columns
    else pd.Series([False] * len(rank_df))
)
overspec = (
    rank_df["suitableButOverspecced"].fillna(False).astype(bool)
    if "suitableButOverspecced" in rank_df.columns
    else pd.Series([False] * len(rank_df))
)
fit = (
    pd.to_numeric(rank_df["fitScoreRaw"], errors="coerce").fillna(0)
    if "fitScoreRaw" in rank_df.columns
    else pd.Series([0] * len(rank_df))
)

fully_count = int(fully.sum())
overspec_count = int(overspec.sum())
near_match_count = int((~fully & (fit >= 80)).sum())

col1, col2, col3, col4, col5, col6, spacer = st.columns([3, 3, 3, 3, 4, 6, 6])
with col1:
    st.metric("Robots shown", int(len(rank_df)))
with col2:
    st.metric("Fully suitable", fully_count)
with col3:
    st.metric("Overspecced", overspec_count)
with col4:
    st.metric("Near match", near_match_count)
with col5:
    st.metric("Weighting", "Equal" if _weights_all_equal(w_norm) else "Custom")
with col6:
    if use_relaxation:
        st.metric("Relaxation", f"P{relax_payload_pct}% / R{relax_reach_pct}% / Rep{relax_precision_pct}%")
    else:
        st.metric("Relaxation", "Off")

# -------------------------
# Top 3
# -------------------------
st.subheader("Top 3 Recommended Robots")
top3 = rank_df.head(3)
for i, (_, row) in enumerate(top3.iterrows()):
    render_robot_card(row, i, app_row=app_row, decorate_top3=True)

# -------------------------
# Table
# -------------------------
st.subheader("Ranked robot shortlist")
preferred_cols = [
    "distanceScore",
    "fullySuitable",
    "suitableButOverspecced",
    "robot",
    "payload",
    "reach",
    "precision",
    "axes",
    "budget",
    "cycleTime",
    "ipRating",
    "cleanroom",
    "esd",
    "forceSensing",
    "robotTypeMatch",
    "notes",
    "weight",
    "mounting",
    "speedGrade",
    "applicationSuitability",
    "safetyFeature",
    "programmingComplexity",
]
cols = [c for c in preferred_cols if c in rank_df.columns]
st.dataframe(rank_df[cols], use_container_width=True, hide_index=True)

# -------------------------
# Download
# -------------------------
csv_bytes = rank_df[cols].to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_bytes,
    file_name=f"robot_ranking_{selected_app_id}.csv",
    mime="text/csv",
)

# -------------------------
# Visuals
# -------------------------
st.divider()
st.subheader("Visualisations")
viz_col1, viz_col2, viz_col3 = st.columns(3)

with viz_col1:
    if "robot" in rank_df.columns and "distanceScore" in rank_df.columns:
        chart_df = rank_df.head(25).set_index("robot")[["distanceScore"]]
        st.bar_chart(chart_df)

with viz_col2:
    if {"reachMm", "payloadKg"}.issubset(rank_df.columns):
        scatter_df = rank_df.head(80)[["reachMm", "payloadKg"]]
        st.scatter_chart(scatter_df)

fig_radar = _build_radar_for_topN(rank_df, N=3)
with viz_col3:
    if fig_radar is not None:
        st.plotly_chart(fig_radar, use_container_width=True)