# app.py
# Streamlit front-end for Neo4j Robot Selection DSS
# Adds:
#  1) Recommended robot highlight + Fit Score %
#  2) Adjustable weighting sliders (payload/reach/precision/axes)
#  3) What-if analysis sliders (relax reach/payload/precision)
#  4) Hard-constraint toggles (now inside a dropdown/expander)
#  5) Simple visualisations (bar chart + scatter payload vs reach)
#  6) CSV download
#
# Top-3 cards:
#  - keep your normal formatted strings for the table
#  - BUT for the Top 3, replace "(req ...)" with "(Δ ...)" and colour ONLY that bracket text:
#       green = better than required
#       white/grey = equal / not applicable
#       red   = does not meet requirement
#
# IMPORTANT:
#  - We return raw numeric fields from Cypher so deltas work for ALL properties
#    (repeatabilityMm, axis, cycleTimeSec, ipRatingNum, costMin/costMax, etc.)

import os
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase
import plotly.graph_objects as go


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


# -------------------------
# Small UI CSS tweaks
# -------------------------
def inject_css():
    st.markdown(
        """
        <style>
          /* Make the app-id dropdown a bit smaller */
          div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            min-height: 30px !important;
            height: 30px !important;
            font-size: 12px !important;
          }
          div[data-testid="stSelectbox"] div[data-baseweb="select"] span {
            font-size: 12px !important;
          }
        </style>
        """,
        unsafe_allow_html=True
    )


# -------------------------
# Helpers
# -------------------------

def _clamp01(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return max(0.0, min(1.0, float(x)))


def _norm_higher_better(robot_val, req_val):
    rv = _to_float(robot_val)
    rq = _to_float(req_val)
    if rv is None or rq is None or rq <= 0:
        return None
    return max(0.0, min(1.0, rv / rq))


def _norm_higher_better(val: Optional[float], req_min: Optional[float]) -> Optional[float]:
    """
    Normalise so:
      - meets requirement => 1.0
      - below requirement => val/req_min (0..1)
      - if req_min missing => None
    """
    if val is None or req_min is None or req_min == 0:
        return None
    if val >= req_min:
        return 1.0
    return _clamp01(val / req_min)


def _norm_lower_better(val: Optional[float], req_max: Optional[float]) -> Optional[float]:
    """
    Normalise so:
      - meets requirement (<=) => 1.0
      - above requirement => req_max/val (0..1)
      - if req_max missing => None
    """
    if val is None or req_max is None or val == 0:
        return None
    if val <= req_max:
        return 1.0
    return _clamp01(req_max / val)


def _build_radar_for_topN(rank_df: pd.DataFrame, N: int = 3) -> Optional[go.Figure]:
    """
    Radar chart comparing Top N robots on normalised (0..1) criteria.
      - 1.0 = meets requirement
      - <1.0 = shortfall
      - >1.0 = exceeds requirement (we clamp to max_val for nicer plots)

    Uses relaxed reqs returned from Cypher where available:
      reqPayloadMinKg, reqReachMinMm, reqRepeatabilityMaxMm, reqAxesMin,
      reqCycleTimeMaxSec, reqIpRatingNum
    """
    if rank_df is None or rank_df.empty:
        return None

    top = rank_df.head(N).copy()

    labels = ["Payload", "Reach", "Repeatability", "Axes", "Cycle time", "IP rating"]
    ideal = [1, 1, 1, 1, 1, 1]

    # More separated, higher-contrast colours (and much lighter fill)
    COLORS = [
        "rgba(66, 165, 245, 0.18)",   # blue fill
        "rgba(255, 202, 40, 0.18)",   # amber fill
        "rgba(239, 83, 80, 0.18)",    # red fill
        "rgba(102, 187, 106, 0.18)",  # green fill
        "rgba(171, 71, 188, 0.18)",   # purple fill
    ]
    LINE_COLORS = [
        "rgba(66, 165, 245, 0.98)",
        "rgba(255, 202, 40, 0.98)",
        "rgba(239, 83, 80, 0.98)",
        "rgba(102, 187, 106, 0.98)",
        "rgba(171, 71, 188, 0.98)",
    ]

    def _clamp01(x: Optional[float], max_val: float = 1.35) -> Optional[float]:
        if x is None:
            return None
        try:
            x = float(x)
        except Exception:
            return None
        if x < 0:
            return 0.0
        if x > max_val:
            return max_val
        return x

    def _norm_higher_better(r_val: Optional[float], req_min: Optional[float]) -> Optional[float]:
        if r_val is None or req_min is None:
            return None
        if req_min == 0:
            return 1.0
        return r_val / req_min

    def _norm_lower_better(r_val: Optional[float], req_max: Optional[float]) -> Optional[float]:
        if r_val is None or req_max is None:
            return None
        if r_val == 0:
            return 1.35
        return req_max / r_val

    fig = go.Figure()

    # ROBOT TRACES FIRST (so requirement line can be drawn ON TOP)
    for i, (_, row) in enumerate(top.iterrows()):
        payload = _to_float(row.get("payloadKg"))
        reach = _to_float(row.get("reachMm"))
        rep = _to_float(row.get("repeatabilityMm"))
        axes = _to_float(row.get("axis"))
        cycle = _to_float(row.get("cycleTimeSec"))
        ip_num = _to_float(row.get("ipRatingNum"))

        req_payload_min = _to_float(row.get("reqPayloadMinKg"))
        req_reach_min = _to_float(row.get("reqReachMinMm"))
        req_rep_max = _to_float(row.get("reqRepeatabilityMaxMm"))
        req_axes_min = _to_float(row.get("reqAxesMin"))
        req_cycle_max = _to_float(row.get("reqCycleTimeMaxSec"))
        req_ip_min = _to_float(row.get("reqIpRatingNum"))

        r_vals = [
            _clamp01(_norm_higher_better(payload, req_payload_min)),
            _clamp01(_norm_higher_better(reach, req_reach_min)),
            _clamp01(_norm_lower_better(rep, req_rep_max)),
            _clamp01(_norm_higher_better(axes, req_axes_min)),
            _clamp01(_norm_lower_better(cycle, req_cycle_max)),
            _clamp01(_norm_higher_better(ip_num, req_ip_min)),
        ]
        r_vals = [0.0 if v is None else float(v) for v in r_vals]

        name = str(row.get("robot", f"Robot {i+1}"))

        fill_col = COLORS[i % len(COLORS)]
        line_col = LINE_COLORS[i % len(LINE_COLORS)]

        fig.add_trace(go.Scatterpolar(
            r=r_vals + [r_vals[0]],
            theta=labels + [labels[0]],
            fill="toself",
            mode="lines+markers",
            marker=dict(size=6),
            line=dict(color=line_col, width=3),   # thicker outline
            fillcolor=fill_col,                   # lighter fill
            name=name,
            hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
        ))

    # REQUIREMENT TRACE LAST (on top, clearer)
    fig.add_trace(go.Scatterpolar(
        r=ideal + [ideal[0]],
        theta=labels + [labels[0]],
        fill=None,
        mode="lines",
        line=dict(
            color="rgba(245,245,245,0.95)",  # bright
            width=3,
        ),
        name="Requirement (meets = 1.0)",
        hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
    ))

    fig.update_layout(
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(220,220,220,0.90)", size=12),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                range=[0, 1.35],
                showline=False,
                gridcolor="rgba(200,200,200,0.18)",
                tickcolor="rgba(200,200,200,0.18)",
                tickfont=dict(color="rgba(200,200,200,0.65)"),
                ticks="outside",
            ),
            angularaxis=dict(
                gridcolor="rgba(200,200,200,0.18)",
                linecolor="rgba(200,200,200,0.18)",
                tickfont=dict(color="rgba(220,220,220,0.90)"),
            ),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(220,220,220,0.90)"),
            orientation="v",
            yanchor="bottom",
            y=0,
            xanchor="left",
            x=0.85,
        ),
        margin=dict(l=20, r=20, t=10, b=10),
    )

    return fig

###
def fmt_fit_score(score: float, fully_suitable: bool) -> str:
    score = float(score)
    if fully_suitable and abs(score - 100.0) < 1e-9:
        return "100.0%"
    score = min(score, 99.9)
    return f"{score:.1f}%"


def _fmt_range(vmin, vmax, unit=""):
    if pd.isna(vmin) and pd.isna(vmax):
        return "—"
    if pd.isna(vmin):
        return f"≤ {vmax}{unit}".strip()
    if pd.isna(vmax):
        return f"≥ {vmin}{unit}".strip()
    return f"{vmin}–{vmax}{unit}".strip()


def _to_float(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() == "none":
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_int(x) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    s = str(x).strip()
    if s == "" or s.lower() == "none":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _norm_req_text(x) -> str:
    if x is None:
        return ""
    return str(x).strip().lower()


def _truthy(x) -> bool:
    s = str(x).strip().lower()
    return s in ["true", "yes", "y", "1"]


def _req_mode(x) -> str:
    """
    Returns: "required" | "optional" | "not_required" | "unknown"
    Works with values like Yes/No/Optional/True/False/null/ISO Class 5 etc.
    """
    s = _norm_req_text(x)
    if s == "":
        return "unknown"
    if "optional" in s:
        return "optional"
    if s in ["no", "false", "0"]:
        return "not_required"
    if s in ["yes", "true", "1", "required"]:
        return "required"
    # for non-boolean fields (e.g. "ISO Class 5") treat as "required" constraint
    return "required"


def _delta_span(delta_text: str, status: str) -> str:
    """
    Colour ONLY the bracket text.
    status: "good" | "bad" | "eq"
    """
    if status == "good":
        color = "rgba(76, 175, 80, 1)"      # green
    elif status == "bad":
        color = "rgba(239, 83, 80, 1)"      # red
    else:
        color = "rgba(255,255,255,0.70)"    # white/grey
    return f"""<span style="color:{color}; font-weight:600;">({delta_text})</span>"""


def _fmt_delta(x: float, unit: str = "") -> str:
    if x is None:
        return "Δ —"
    if abs(x) < 1e-12:
        return f"Δ 0{unit}".strip()
    sign = "+" if x > 0 else ""
    return f"Δ {sign}{x:g}{unit}".strip()


def _compare_range_robot_value(
    r_val: Optional[float],
    req_min: Optional[float],
    req_max: Optional[float],
    higher_is_better_outside_max: bool,
    unit: str
) -> Tuple[str, str]:
    """
    - If below min => bad (Δ = r - min)
    - If within [min,max] => eq (Δ 0)
    - If above max:
        if higher_is_better_outside_max => good
        else => bad
    """
    if r_val is None or req_min is None:
        return "—", _delta_span("Δ —", "eq")

    if r_val < req_min:
        d = r_val - req_min
        return f"{r_val:g}{unit}", _delta_span(_fmt_delta(d, unit), "bad")

    if req_max is not None and r_val > req_max:
        d = r_val - req_max
        status = "good" if higher_is_better_outside_max else "bad"
        return f"{r_val:g}{unit}", _delta_span(_fmt_delta(d, unit), status)

    return f"{r_val:g}{unit}", _delta_span("Δ 0", "eq")


def _compare_upper_bound_lower_is_better(
    r_val: Optional[float],
    req_max: Optional[float],
    unit: str
) -> Tuple[str, str]:
    if r_val is None or req_max is None:
        return "—", _delta_span("Δ —", "eq")
    d = r_val - req_max
    if d > 0:
        return f"{r_val:g}{unit}", _delta_span(_fmt_delta(d, unit), "bad")
    if d < 0:
        return f"{r_val:g}{unit}", _delta_span(_fmt_delta(d, unit), "good")
    return f"{r_val:g}{unit}", _delta_span("Δ 0", "eq")


def _compare_min_bound_higher_is_better(
    r_val: Optional[float],
    req_min: Optional[float],
    unit: str
) -> Tuple[str, str]:
    if r_val is None or req_min is None:
        return "—", _delta_span("Δ —", "eq")
    d = r_val - req_min
    if d < 0:
        return f"{int(r_val)}{unit}", _delta_span(_fmt_delta(d, unit), "bad")
    if d > 0:
        return f"{int(r_val)}{unit}", _delta_span(_fmt_delta(d, unit), "good")
    return f"{int(r_val)}{unit}", _delta_span("Δ 0", "eq")


def _compare_ip_num(r_ip_num: Optional[int], req_ip_num: Optional[int]) -> Tuple[str, str]:
    if r_ip_num is None or req_ip_num is None:
        return ("—" if r_ip_num is None else f"IP{r_ip_num}"), _delta_span("Δ —", "eq")
    d = r_ip_num - req_ip_num
    if d < 0:
        return f"IP{r_ip_num}", _delta_span(_fmt_delta(d, ""), "bad")
    if d > 0:
        return f"IP{r_ip_num}", _delta_span(_fmt_delta(d, ""), "good")
    return f"IP{r_ip_num}", _delta_span("Δ 0", "eq")


def _compare_budget_overlap(
    cost_min: Optional[float],
    cost_max: Optional[float],
    a_min: Optional[float],
    a_max: Optional[float]
) -> Tuple[str, str]:
    if cost_min is None or cost_max is None or a_min is None or a_max is None:
        return "—", _delta_span("Δ —", "eq")

    overlap = (cost_min <= a_max) and (cost_max >= a_min)
    if overlap:
        return f"{cost_min:g}–{cost_max:g} USD", _delta_span("Δ 0", "eq")

    if cost_min > a_max:
        d = cost_min - a_max
        return f"{cost_min:g}–{cost_max:g} USD", _delta_span(_fmt_delta(d, " USD"), "bad")

    if cost_max < a_min:
        d = cost_max - a_min  # negative
        return f"{cost_min:g}–{cost_max:g} USD", _delta_span(_fmt_delta(d, " USD"), "bad")

    return f"{cost_min:g}–{cost_max:g} USD", _delta_span("Δ —", "eq")


def _compare_feature_req(robot_val, app_req_val) -> Tuple[str, str]:
    mode = _req_mode(app_req_val)
    rv = "—" if robot_val is None else str(robot_val)

    if mode in ["optional", "not_required", "unknown"]:
        return rv, _delta_span("Δ 0", "eq")

    ok = _truthy(robot_val)
    return rv, _delta_span("Δ 0", "good" if ok else "bad")


def _compare_type(robot_type: str, app_type_req) -> Tuple[str, str]:
    rt = (robot_type or "").strip()
    at = "" if app_type_req is None else str(app_type_req).strip()
    if at == "":
        return rt if rt else "—", _delta_span("Δ 0", "eq")

    ok = rt.lower() in at.lower() or at.lower() in rt.lower()
    return rt if rt else "—", _delta_span("Δ 0", "eq" if ok else "bad")


# -------------------------
# Rendering
# -------------------------
def render_robot_card(row, rank_idx: int, app_row: Optional[dict] = None, decorate_top3: bool = False):
    fully = bool(row.get("fullySuitable", False))
    score = float(row.get("fitScoreRaw", 0.0)) if "fitScoreRaw" in row else (
        100.0 * (1.0 - float(row.get("distanceScore", 0.0)))
    )
    score_txt = fmt_fit_score(score, fully)

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

    payload_txt = row.get("payload", "—")
    reach_txt = row.get("reach", "—")
    precision_txt = row.get("precision", "—")
    axes_txt = row.get("axes", "—")
    budget_txt = row.get("budget", "—")
    cycle_txt = row.get("cycleTime", "—")
    ip_txt = row.get("ipRating", "—")
    cleanroom_txt = row.get("cleanroom", "—")
    esd_txt = row.get("esd", "—")
    force_txt = row.get("forceSensing", "—")
    type_match_txt = row.get("robotTypeMatch", "—")

    if decorate_top3 and app_row is not None:
        r_payload = _to_float(row.get("payloadKg"))
        r_reach = _to_float(row.get("reachMm"))
        r_rep = _to_float(row.get("repeatabilityMm"))
        r_axes = _to_int(row.get("axis"))
        r_cycle = _to_float(row.get("cycleTimeSec"))

        r_ip_num = _to_int(row.get("ipRatingNum"))
        r_clean_raw = row.get("cleanroomOptionRaw", row.get("cleanroomOption", None))
        r_esd_raw = row.get("esdSafeRaw", row.get("esdSafe", None))
        r_force_raw = row.get("forceSensingRaw", row.get("forceSensing", None))
        r_type_raw = row.get("robotType", row.get("robotType", ""))

        cost_min = _to_float(row.get("costMin"))
        cost_max = _to_float(row.get("costMax"))

        a_pmin = _to_float(app_row.get("payloadMinKg"))
        a_pmax = _to_float(app_row.get("payloadMaxKg"))
        a_rmin = _to_float(app_row.get("reachMinMm"))
        a_rmax = _to_float(app_row.get("reachMaxMm"))
        a_rep_req = _to_float(app_row.get("repeatabilityRequiredMm"))
        a_axes_min = _to_int(app_row.get("axesMin"))
        a_cycle_req = _to_float(app_row.get("cycleTimeTargetSec"))

        # IMPORTANT: use the parsed req ip from Cypher (row), not app_row text
        a_ip_req_num = _to_int(row.get("reqIpRatingNum"))

        a_budget_min = _to_float(app_row.get("budgetMinUsd"))
        a_budget_max = _to_float(app_row.get("budgetMaxUsd"))

        a_clean_req = app_row.get("cleanroomRequired")
        a_esd_req = app_row.get("esdProtection")
        a_force_req = app_row.get("forceSensingRequired")
        a_type_req = app_row.get("typicalRobotType")

        p_val, p_delta = _compare_range_robot_value(
            r_payload, a_pmin, a_pmax, higher_is_better_outside_max=True, unit=" kg"
        )
        payload_txt = f"{p_val} {p_delta}"

        r_val, r_delta = _compare_range_robot_value(
            r_reach, a_rmin, a_rmax, higher_is_better_outside_max=True, unit=" mm"
        )
        reach_txt = f"{r_val} {r_delta}"

        rep_val, rep_delta = _compare_upper_bound_lower_is_better(r_rep, a_rep_req, " mm")
        precision_txt = f"{rep_val} {rep_delta}"

        ax_val, ax_delta = _compare_min_bound_higher_is_better(
            float(r_axes) if r_axes is not None else None,
            float(a_axes_min) if a_axes_min is not None else None,
            ""
        )
        axes_txt = f"{ax_val} {ax_delta}"

        b_val, b_delta = _compare_budget_overlap(cost_min, cost_max, a_budget_min, a_budget_max)
        budget_txt = f"{b_val} {b_delta}" if b_val != "—" else (row.get("budget") or "—")

        cy_val, cy_delta = _compare_upper_bound_lower_is_better(r_cycle, a_cycle_req, " s")
        cycle_txt = f"{cy_val} {cy_delta}"

        ip_val, ip_delta = _compare_ip_num(r_ip_num, a_ip_req_num)
        ip_txt = f"{ip_val} {ip_delta}"

        cl_val, cl_delta = _compare_feature_req(r_clean_raw, a_clean_req)
        cleanroom_txt = f"{cl_val} {cl_delta}"

        esd_val, esd_delta = _compare_feature_req(r_esd_raw, a_esd_req)
        esd_txt = f"{esd_val} {esd_delta}"

        fo_val, fo_delta = _compare_feature_req(r_force_raw, a_force_req)
        force_txt = f"{fo_val} {fo_delta}"

        ty_val, ty_delta = _compare_type(str(r_type_raw), a_type_req)
        type_match_txt = f"{ty_val} {ty_delta}"

    medal = "🥇" if rank_idx == 0 else ("🥈" if rank_idx == 1 else "🥉")

    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-left: 6px solid {border};
            border-radius: 14px;
            padding: 16px;
            margin: 10px 0;
        ">
          <div style="display:flex; justify-content:space-between;">
            <div>
              <div style="font-size:18px; font-weight:700;">
                {medal} {robot}
              </div>
              <div style="font-size:13px; opacity:0.85;">
                {badge} · {rtype} · {manu}
              </div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:12px;">Fit score</div>
              <div style="font-size:24px; font-weight:800;">
                {score_txt}
              </div>
            </div>
          </div>
          <div style="
            margin-top:12px;
            display:grid;
            grid-template-columns: 180px 1fr 180px 1fr;
            row-gap:6px;
            column-gap:12px;
            font-size:13px;
          ">
            <div>Payload</div><div>{payload_txt}</div>
            <div>Reach</div><div>{reach_txt}</div>
            <div>Repeatability</div><div>{precision_txt}</div>
            <div>Axes</div><div>{axes_txt}</div>
            <div>Budget</div><div>{budget_txt}</div>
            <div>Cycle time</div><div>{cycle_txt}</div>
            <div>IP rating</div><div>{ip_txt}</div>
            <div>Cleanroom</div><div>{cleanroom_txt}</div>
            <div>ESD</div><div>{esd_txt}</div>
            <div>Force sensing</div><div>{force_txt}</div>
            <div>Robot type</div><div>{type_match_txt}</div>
            <div></div><div></div>
          </div>
          <div style="margin-top:10px; font-size:12px; opacity:0.85;">
            <b>Notes:</b> {notes}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_application_box(app_row: dict):
    app_id = app_row.get("applicationId", "—")
    app_type = app_row.get("applicationType", "") or ""
    sector = app_row.get("industrySector", "") or ""

    payload_req = _fmt_range(app_row.get("payloadMinKg"), app_row.get("payloadMaxKg"), " kg")
    reach_req = _fmt_range(app_row.get("reachMinMm"), app_row.get("reachMaxMm"), " mm")

    rep_req = app_row.get("repeatabilityRequiredMm")
    rep_txt = "—" if pd.isna(rep_req) else f"≤ {rep_req} mm"

    axes_min = app_row.get("axesMin")
    axes_txt = "—" if pd.isna(axes_min) else f"≥ {int(axes_min)}"

    budget_txt = _fmt_range(app_row.get("budgetMinUsd"), app_row.get("budgetMaxUsd"), " USD")

    ct = app_row.get("cycleTimeTargetSec")
    cycle_txt = "—" if pd.isna(ct) else f"≤ {ct} s"

    ipmin = app_row.get("ipRatingMin")
    ip_txt = "—" if (ipmin is None or str(ipmin).strip() == "") else f"≥ {ipmin}"

    cleanroom = app_row.get("cleanroomRequired")
    esd = app_row.get("esdProtection")
    force = app_row.get("forceSensingRequired")
    rtype = app_row.get("typicalRobotType")
    speed = app_row.get("speedPriority")
    safety = app_row.get("safetyClassification")

    bg = "rgba(30, 58, 138, 0.04)"
    border = "rgba(30, 58, 138, 0.35)"

    st.markdown(
        f"""
        <div style="
            background:{bg};
            border: 1px solid {border};
            border-radius: 14px;
            padding: 14px 16px;
            margin: 12px 0 6px 0;
        ">
          <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
            <div>
              <div style="font-size:18px; font-weight:800;">Application {app_id} — {app_type}</div>
              <div style="opacity:0.8; font-size:13px;">{sector}</div>
            </div>
          </div>
          <div style="margin-top:12px; display:grid; grid-template-columns: 180px 1fr 180px 1fr; row-gap:8px; column-gap:14px; font-size:13px;">
            <div style="opacity:0.85;">Payload required</div><div>{payload_req}</div>
            <div style="opacity:0.85;">Reach required</div><div>{reach_req}</div>
            <div style="opacity:0.85;">Repeatability required</div><div>{rep_txt}</div>
            <div style="opacity:0.85;">Axes minimum</div><div>{axes_txt}</div>
            <div style="opacity:0.85;">Budget</div><div>{budget_txt}</div>
            <div style="opacity:0.85;">Cycle time target</div><div>{cycle_txt}</div>
            <div style="opacity:0.85;">IP rating minimum</div><div>{ip_txt}</div>
            <div style="opacity:0.85;">Typical robot type</div><div>{rtype or "—"}</div>
            <div style="opacity:0.85;">Cleanroom</div><div>{cleanroom if cleanroom is not None else "—"}</div>
            <div style="opacity:0.85;">ESD protection</div><div>{esd if esd is not None else "—"}</div>
            <div style="opacity:0.85;">Force sensing</div><div>{force if force is not None else "—"}</div>
            <div style="opacity:0.85;">Speed priority</div><div>{speed if speed is not None else "—"}</div>
            <div style="opacity:0.85;">Safety class</div><div>{safety if safety is not None else "—"}</div>
            <div></div><div></div>
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

Q_GET_APPLICATION_DETAILS = """
MATCH (a:ApplicationRequirement {applicationId: $appId})
RETURN
  a.applicationId AS applicationId,
  a.applicationType AS applicationType,
  a.industrySector AS industrySector,

  a.payloadMinKg AS payloadMinKg,
  a.payloadMaxKg AS payloadMaxKg,
  a.reachMinMm AS reachMinMm,
  a.reachMaxMm AS reachMaxMm,
  a.repeatabilityRequiredMm AS repeatabilityRequiredMm,
  a.axesMin AS axesMin,

  a.budgetMinUsd AS budgetMinUsd,
  a.budgetMaxUsd AS budgetMaxUsd,
  a.cycleTimeTargetSec AS cycleTimeTargetSec,
  a.ipRatingMin AS ipRatingMin,

  a.cleanroomRequired AS cleanroomRequired,
  a.esdProtection AS esdProtection,
  a.forceSensingRequired AS forceSensingRequired,
  a.typicalRobotType AS typicalRobotType,
  a.speedPriority AS speedPriority,
  a.safetyClassification AS safetyClassification
LIMIT 1;
"""

# NOTE: This query includes:
#  - parsed IP numeric (ipRobot/ipReq)
#  - robust passType based on base tokens (scara / 6-axis / cobot)
#  - hard constraint toggles applied via WHERE clause (correct Cypher syntax)
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

WITH r, a, relaxReach, relaxPayload, relaxPrecision,
     wPayload, wReach, wPrecision, wAxes,
     0.18 AS wBudget,
     0.18 AS wCycle,
     0.06 AS wIP,
     0.06 AS wCleanroom,
     0.06 AS wESD,
     0.06 AS wForce,
     0.06 AS wType

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,

     (a.payloadMinKg * (1 - relaxPayload)) AS payloadMinR,
     (a.payloadMaxKg * (1 + relaxPayload)) AS payloadMaxR,
     (a.reachMinMm * (1 - relaxReach)) AS reachMinR,
     (a.reachMaxMm * (1 + relaxReach)) AS reachMaxR,
     (a.repeatabilityRequiredMm * (1 + relaxPrecision)) AS repReqR,
     a.axesMin AS axesMinR

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,

     toLower(toString(coalesce(r.cleanroomOption, "false"))) AS rCleanStr,
     toLower(toString(coalesce(r.esdSafe, "false")))         AS rEsdStr,
     toLower(toString(coalesce(r.forceSensing, "false")))    AS rForceStr,

     toLower(toString(coalesce(a.cleanroomRequired, "false")))      AS aCleanStr,
     toLower(toString(coalesce(a.esdProtection, "false")))          AS aEsdStr,
     toLower(toString(coalesce(a.forceSensingRequired, "false")))   AS aForceStr

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,

     (rCleanStr IN ["true","yes","y","1"]) AS rCleanOK,
     (rEsdStr   IN ["true","yes","y","1"]) AS rEsdOK,
     (rForceStr IN ["true","yes","y","1"]) AS rForceOK,

     (aCleanStr IN ["true","yes","y","1"]) AS aCleanReq,
     (aEsdStr   IN ["true","yes","y","1"]) AS aEsdReq,
     (aForceStr IN ["true","yes","y","1"]) AS aForceReq

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,

     toLower(replace(replace(replace(replace(toString(coalesce(r.costRangeUsd,"")), "–", "-"), "$",""), ",",""), " ", "")) AS costStr0

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,

     replace(costStr0, "k", "000") AS costStr

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,
     [x IN split(costStr, "-") | trim(x)] AS costParts

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,

     CASE WHEN size(costParts)=0 OR costParts[0]="" THEN null ELSE toFloat(costParts[0]) END AS costMin,
     CASE
       WHEN size(costParts) < 2 OR costParts[1] = "" THEN
         CASE WHEN size(costParts)=0 OR costParts[0]="" THEN null ELSE toFloat(costParts[0]) END
       ELSE toFloat(costParts[1])
     END AS costMax

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,
     costMin, costMax,

     // IP is always IPXX -> strip "IP" and parse digits
     toInteger(replace(toUpper(toString(coalesce(r.ipRating,"IP0"))), "IP", "")) AS ipRobot,
     toInteger(replace(toUpper(toString(coalesce(a.ipRatingMin,"IP0"))), "IP", "")) AS ipReq

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     rCleanOK, rEsdOK, rForceOK, aCleanReq, aEsdReq, aForceReq,
     costMin, costMax, ipRobot, ipReq,

     // hard constraint toggles (from params)
     $hardPayload AS hardPayload,
     $hardReach AS hardReach,
     $hardPrecision AS hardPrecision,
     $hardAxes AS hardAxes,

     $hardBudget AS hardBudget,
     $hardCycle AS hardCycle,
     $hardIP AS hardIP,

     $hardCleanroom AS hardCleanroom,
     $hardESD AS hardESD,
     $hardForce AS hardForce,

     $hardType AS hardType,

     // passes
     (r.payloadKg >= payloadMinR AND r.payloadKg <= payloadMaxR) AS passPayload,
     (r.reachMm   >= reachMinR   AND r.reachMm   <= reachMaxR)   AS passReach,
     (r.repeatabilityMm <= repReqR)                              AS passPrecision,
     (r.axis >= axesMinR)                                        AS passAxes,

     CASE
       WHEN a.budgetMinUsd IS NULL OR a.budgetMaxUsd IS NULL OR costMin IS NULL OR costMax IS NULL THEN true
       ELSE (costMin <= a.budgetMaxUsd AND costMax >= a.budgetMinUsd)
     END AS passBudget,

     CASE
       WHEN a.cycleTimeTargetSec IS NULL OR r.cycleTimeSec IS NULL THEN true
       ELSE (r.cycleTimeSec <= a.cycleTimeTargetSec)
     END AS passCycle,

     CASE WHEN aCleanReq THEN rCleanOK ELSE true END AS passCleanroom,
     CASE WHEN aEsdReq   THEN rEsdOK   ELSE true END AS passESD,
     CASE WHEN aForceReq THEN rForceOK ELSE true END AS passForce,

     CASE
       WHEN a.ipRatingMin IS NULL THEN true
       ELSE (ipRobot >= ipReq)
     END AS passIP,

     // ROBOT TYPE MATCH:
     // allow apps like "SCARA; Compact 6-axis" to match either scara OR 6-axis
     CASE
       WHEN a.typicalRobotType IS NULL OR trim(toString(a.typicalRobotType)) = "" THEN true
       ELSE
         any(reqBase IN
           [tok IN split(
               replace(replace(replace(toLower(toString(a.typicalRobotType)),"/", ";"), ",", ";"), "  ", " "),
               ";"
            ) |
            CASE
              WHEN trim(tok) = "" THEN ""
              WHEN tok CONTAINS "scara" THEN "scara"
              WHEN tok CONTAINS "6-axis" OR tok CONTAINS "6 axis" OR tok CONTAINS "6axis" THEN "6-axis"
              WHEN tok CONTAINS "cobot" THEN "cobot"
              ELSE trim(tok)
            END
           ]
           WHERE reqBase <> "" AND reqBase = toLower(trim(toString(r.type)))
         )
     END AS passType

WITH r, a, payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, ipRobot, ipReq,
     passPayload, passReach, passPrecision, passAxes,
     passBudget, passCycle, passCleanroom, passESD, passForce, passIP, passType,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     hardPayload, hardReach, hardPrecision, hardAxes,
     hardBudget, hardCycle, hardIP,
     hardCleanroom, hardESD, hardForce,
     hardType

WHERE
    (NOT hardPayload OR passPayload)
AND (NOT hardReach OR passReach)
AND (NOT hardPrecision OR passPrecision)
AND (NOT hardAxes OR passAxes)

AND (NOT hardBudget OR passBudget)
AND (NOT hardCycle OR passCycle)
AND (NOT hardIP OR passIP)

AND (NOT hardCleanroom OR passCleanroom)
AND (NOT hardESD OR passESD)
AND (NOT hardForce OR passForce)

AND (NOT hardType OR passType)

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, ipRobot, ipReq,
     passPayload, passReach, passPrecision, passAxes,
     passBudget, passCycle, passCleanroom, passESD, passForce, passIP, passType,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,

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
     END AS axesGap,

     CASE
       WHEN a.budgetMinUsd IS NULL OR a.budgetMaxUsd IS NULL OR costMin IS NULL OR costMax IS NULL THEN 0
       WHEN costMin > a.budgetMaxUsd THEN (costMin - a.budgetMaxUsd) / a.budgetMaxUsd
       WHEN costMax < a.budgetMinUsd THEN (a.budgetMinUsd - costMax) / a.budgetMinUsd
       ELSE 0
     END AS budgetGap,

     CASE
       WHEN a.cycleTimeTargetSec IS NULL OR r.cycleTimeSec IS NULL THEN 0
       WHEN r.cycleTimeSec > a.cycleTimeTargetSec THEN (r.cycleTimeSec - a.cycleTimeTargetSec) / a.cycleTimeTargetSec
       ELSE 0
     END AS cycleGap,

     CASE WHEN passCleanroom THEN 0 ELSE 1 END AS cleanroomGap,
     CASE WHEN passESD THEN 0 ELSE 1 END AS esdGap,
     CASE WHEN passForce THEN 0 ELSE 1 END AS forceGap,

     CASE
       WHEN a.ipRatingMin IS NULL THEN 0
       WHEN ipRobot < ipReq AND ipReq > 0 THEN (ipReq - ipRobot) * 1.0 / ipReq
       ELSE 0
     END AS ipGap,

     CASE WHEN passType THEN 0 ELSE 1 END AS typeGap

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, ipRobot, ipReq,
     passPayload, passReach, passPrecision, passAxes,
     passBudget, passCycle, passCleanroom, passESD, passForce, passIP, passType,
     payloadGap, reachGap, precisionGap, axesGap,
     budgetGap, cycleGap, ipGap, cleanroomGap, esdGap, forceGap, typeGap,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,

     (wPayload+wReach+wPrecision+wAxes+wBudget+wCycle+wIP+wCleanroom+wESD+wForce+wType) AS wTotal

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, ipRobot, ipReq,
     passPayload, passReach, passPrecision, passAxes,
     passBudget, passCycle, passCleanroom, passESD, passForce, passIP, passType,
     payloadGap, reachGap, precisionGap, axesGap,
     budgetGap, cycleGap, ipGap, cleanroomGap, esdGap, forceGap, typeGap,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     wTotal,

     (
       wPayload*payloadGap +
       wReach*reachGap +
       wPrecision*precisionGap +
       wAxes*axesGap +
       wBudget*budgetGap +
       wCycle*cycleGap +
       wIP*ipGap +
       wCleanroom*cleanroomGap +
       wESD*esdGap +
       wForce*forceGap +
       wType*typeGap
     ) / CASE WHEN wTotal = 0 THEN 1 ELSE wTotal END AS distanceScoreRaw,

     (
       passPayload AND passReach AND passPrecision AND passAxes AND
       passBudget AND passCycle AND passCleanroom AND passESD AND passForce AND passIP AND passType
     ) AS fullySuitable,

     [
       CASE WHEN NOT passPayload THEN "Payload out of range" END,
       CASE WHEN NOT passReach THEN "Reach out of range" END,
       CASE WHEN NOT passPrecision THEN "Repeatability not sufficient" END,
       CASE WHEN NOT passAxes THEN "Insufficient axes" END,
       CASE WHEN NOT passBudget THEN "Budget mismatch" END,
       CASE WHEN NOT passCycle THEN "Cycle time too slow" END,
       CASE WHEN NOT passIP THEN "IP rating too low" END,
       CASE WHEN NOT passCleanroom THEN "Cleanroom required" END,
       CASE WHEN NOT passESD THEN "ESD protection required" END,
       CASE WHEN NOT passForce THEN "Force sensing required" END,
       CASE WHEN NOT passType THEN "Robot type mismatch" END
     ] AS rawReasons

WITH r, a, payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, ipRobot, ipReq,
     fullySuitable, distanceScoreRaw,
     [x IN rawReasons WHERE x IS NOT NULL] AS reasons

RETURN
  a.applicationId   AS appId,
  a.applicationType AS applicationType,

  r.robotModel      AS robot,
  r.type            AS robotType,
  r.manufacturer    AS manufacturer,
  fullySuitable,

  r.payloadKg         AS payloadKg,
  r.reachMm           AS reachMm,
  r.repeatabilityMm   AS repeatabilityMm,
  r.axis              AS axis,
  r.cycleTimeSec      AS cycleTimeSec,

  costMin             AS costMin,
  costMax             AS costMax,

  r.cleanroomOption   AS cleanroomOptionRaw,
  r.esdSafe           AS esdSafeRaw,
  r.forceSensing      AS forceSensingRaw,

  ipRobot             AS ipRatingNum,
  r.type              AS robotTypeRaw,

  payloadMinR          AS reqPayloadMinKg,
  payloadMaxR          AS reqPayloadMaxKg,
  reachMinR            AS reqReachMinMm,
  reachMaxR            AS reqReachMaxMm,
  repReqR              AS reqRepeatabilityMaxMm,
  axesMinR             AS reqAxesMin,

  a.budgetMinUsd       AS reqBudgetMinUsd,
  a.budgetMaxUsd       AS reqBudgetMaxUsd,
  a.cycleTimeTargetSec AS reqCycleTimeMaxSec,

  ipReq                AS reqIpRatingNum,

  a.cleanroomRequired  AS reqCleanroom,
  a.esdProtection      AS reqEsd,
  a.forceSensingRequired AS reqForceSensing,
  a.typicalRobotType   AS reqRobotType,

  toString(r.payloadKg) + " kg (req " +
    toString(round(payloadMinR*100)/100.0) + "–" +
    toString(round(payloadMaxR*100)/100.0) + " kg)" AS payload,

  toString(r.reachMm) + " mm (req " +
    toString(round(reachMinR)) + "–" +
    toString(round(reachMaxR)) + " mm)" AS reach,

  toString(r.repeatabilityMm) + " mm (req ≤ " +
    toString(round(repReqR*1000)/1000.0) + " mm)" AS precision,

  toString(r.axis) + " (req ≥ " + toString(axesMinR) + ")" AS axes,

  CASE
    WHEN costMin IS NULL OR costMax IS NULL OR a.budgetMinUsd IS NULL OR a.budgetMaxUsd IS NULL THEN "—"
    ELSE toString(round(costMin)) + "–" + toString(round(costMax)) +
         " USD (req " + toString(a.budgetMinUsd) + "–" + toString(a.budgetMaxUsd) + " USD)"
  END AS budget,

  CASE
    WHEN r.cycleTimeSec IS NULL OR a.cycleTimeTargetSec IS NULL THEN "—"
    ELSE toString(r.cycleTimeSec) + " s (req ≤ " + toString(a.cycleTimeTargetSec) + " s)"
  END AS cycleTime,

  CASE
    WHEN a.ipRatingMin IS NULL OR ipReq IS NULL OR ipRobot IS NULL THEN "—"
    ELSE "IP" + toString(ipRobot) + " (req ≥ IP" + toString(ipReq) + ")"
  END AS ipRating,

  CASE
    WHEN a.cleanroomRequired IS NULL THEN "—"
    ELSE toString(r.cleanroomOption) + " (req " + toString(a.cleanroomRequired) + ")"
  END AS cleanroom,

  CASE
    WHEN a.esdProtection IS NULL THEN "—"
    ELSE toString(r.esdSafe) + " (req " + toString(a.esdProtection) + ")"
  END AS esd,

  CASE
    WHEN a.forceSensingRequired IS NULL THEN "—"
    ELSE toString(r.forceSensing) + " (req " + toString(a.forceSensingRequired) + ")"
  END AS forceSensing,

  CASE
    WHEN a.typicalRobotType IS NULL OR trim(toString(a.typicalRobotType)) = "" THEN "—"
    ELSE toString(r.type) + " (req " + toString(a.typicalRobotType) + ")"
  END AS robotTypeMatch,

  CASE
    WHEN fullySuitable THEN "Meets all requirements"
    ELSE reduce(s="", rr IN reasons | CASE WHEN s="" THEN rr ELSE s + "; " + rr END)
  END AS notes,

  round(distanceScoreRaw*10000)/10000 AS distanceScore,

  CASE
    WHEN distanceScoreRaw <= 0 THEN 100.0
    WHEN distanceScoreRaw >= 1 THEN 0.0
    ELSE (1 - distanceScoreRaw) * 100.0
  END AS fitScoreRaw

ORDER BY fullySuitable DESC, distanceScoreRaw ASC, robot
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
inject_css()

if "driver" not in st.session_state:
    st.session_state.driver = None
if "conn_error" not in st.session_state:
    st.session_state.conn_error = None


# Sidebar
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
        uri = st.text_input("Neo4j URI", value=DEFAULT_URI, placeholder="neo4j+s://xxxx.databases.neo4j.io")
        user = st.text_input("Username", value=DEFAULT_USER or "neo4j")
        password = st.text_input("Password", value=DEFAULT_PASSWORD, type="password")

    st.divider()
    st.header("Ranking controls")

    limit = st.slider("Max results", min_value=10, max_value=200, value=50, step=10)

    # -------------------------
    # Hard constraints
    # -------------------------
    with st.expander("Hard constraints", expanded=False):

        # Initialise session state
        if "hard_all" not in st.session_state:
            st.session_state.hard_all = False

        constraint_keys = [
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
            "hard_type"
        ]

        # Initialise individual toggles
        for key in constraint_keys:
            if key not in st.session_state:
                st.session_state[key] = False


        # ---------- MASTER CHECKBOX ----------
        def master_changed():
            for key in constraint_keys:
                st.session_state[key] = st.session_state.hard_all

        # ---------- INDIVIDUAL TOGGLES ----------
        def individual_changed():
            st.session_state.hard_all = False


        st.toggle("Payload", key="hard_payload", on_change=individual_changed)
        st.toggle("Reach", key="hard_reach", on_change=individual_changed)
        st.toggle("Repeatability", key="hard_precision", on_change=individual_changed)
        st.toggle("Axes", key="hard_axes", on_change=individual_changed)

        st.toggle("Budget", key="hard_budget", on_change=individual_changed)
        st.toggle("Cycle time", key="hard_cycle", on_change=individual_changed)
        st.toggle("IP rating", key="hard_ip", on_change=individual_changed)

        st.toggle("Cleanroom (if required)", key="hard_cleanroom", on_change=individual_changed)
        st.toggle("ESD (if required)", key="hard_esd", on_change=individual_changed)
        st.toggle("Force sensing (if required)", key="hard_force", on_change=individual_changed)

        st.toggle("Robot type", key="hard_type", on_change=individual_changed)

        st.checkbox(
                "Apply all",
                key="hard_all",
                on_change=master_changed,
                help="When enabled, robots must meet all selected requirements."
            )

    # Assign variables for query params
    hard_payload   = st.session_state.hard_payload
    hard_reach     = st.session_state.hard_reach
    hard_precision = st.session_state.hard_precision
    hard_axes      = st.session_state.hard_axes

    hard_budget    = st.session_state.hard_budget
    hard_cycle     = st.session_state.hard_cycle
    hard_ip        = st.session_state.hard_ip

    hard_cleanroom = st.session_state.hard_cleanroom
    hard_esd       = st.session_state.hard_esd
    hard_force     = st.session_state.hard_force

    hard_type      = st.session_state.hard_type

    st.subheader("Weighting")

    use_weighting = st.toggle(
        "Enable custom weighting",
        value=False,
        help="Turn on to prioritise certain criteria over others"
    )

    if use_weighting:
        st.caption("Adjust importance of each criterion")
        w_payload = st.slider("Payload importance", 0.0, 1.0, 0.30, 0.05)
        w_reach = st.slider("Reach importance", 0.0, 1.0, 0.25, 0.05)
        w_precision = st.slider("Precision importance", 0.0, 1.0, 0.35, 0.05)
        w_axes = st.slider("Axes importance", 0.0, 1.0, 0.10, 0.05)
    else:
        w_payload = 0.25
        w_reach = 0.25
        w_precision = 0.25
        w_axes = 0.25

    st.subheader("What-if relaxation (%)")
    relax_payload_pct = st.slider("Relax payload range", 0, 50, 0, 1)
    relax_reach_pct = st.slider("Relax reach range", 0, 50, 0, 1)
    relax_precision_pct = st.slider("Relax repeatability requirement", 0, 50, 0, 1)


# Auto-connect
if st.session_state.driver is None and have_env_creds:
    try:
        st.session_state.driver = GraphDatabase.driver(uri, auth=(user, password))
        _ = run_query(st.session_state.driver, "RETURN 1 AS ok;", database=NEO4J_DATABASE)
        st.session_state.conn_error = None
    except Exception as e:
        st.session_state.driver = None
        st.session_state.conn_error = str(e)

driver = st.session_state.driver
if driver is None:
    if st.session_state.conn_error:
        st.error(f"Not connected: {st.session_state.conn_error}")
    else:
        st.error("Not connected: missing credentials.")
    st.stop()


# Load applications
apps_df = run_query(driver, Q_LIST_APPLICATIONS, database=NEO4J_DATABASE)
apps_df["applicationType"] = apps_df["applicationType"].fillna("")
app_ids = apps_df["applicationId"].tolist()


# -------------------------
# HEADER ROW
# -------------------------
col_title, col_status, col_select = st.columns([12, 5, 1], vertical_alignment="center")

with col_title:
    st.markdown("<h1 style='margin-bottom:0px;'>Robot Selection</h1>", unsafe_allow_html=True)

with col_status:
    connected = (driver is not None)
    weight_txt = "Custom weighting" if use_weighting else "Equal weighting"
    conn_txt = "Connected" if connected else "Not connected"

    st.markdown(
        f"""
        <div style="display:flex; justify-content:flex-end; gap:8px; align-items:center; margin-top:8px;">
          <span style="
            padding:4px 10px;
            border-radius:999px;
            font-size:12px;
            font-weight:600;
            background: rgba(46,125,50,0.10);
            color: rgba(46,125,50,1);
            border: 1px solid rgba(46,125,50,0.25);
          ">{conn_txt}</span>

          <span style="
            padding:4px 10px;
            border-radius:999px;
            font-size:12px;
            font-weight:600;
            background: rgba(30,58,138,0.08);
            color: rgba(160,190,255,1);
            border: 1px solid rgba(30,58,138,0.22);
          ">{weight_txt}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_select:
    selected_app_id = st.selectbox("", app_ids, label_visibility="collapsed")


# -------------------------
# APPLICATION BOX
# -------------------------
app_details_df = run_query(
    driver,
    Q_GET_APPLICATION_DETAILS,
    {"appId": selected_app_id},
    database=NEO4J_DATABASE
)
if app_details_df.empty:
    st.error("No application details found for selected application ID.")
    st.stop()

app_row = app_details_df.iloc[0].to_dict()
render_application_box(app_row)


# -------------------------
# WEIGHT NORMALISATION
# -------------------------
w_sum = float(w_payload + w_reach + w_precision + w_axes)
if w_sum <= 0:
    w_payload_n = w_reach_n = w_precision_n = w_axes_n = 0.25
else:
    w_payload_n = w_payload / w_sum
    w_reach_n = w_reach / w_sum
    w_precision_n = w_precision / w_sum
    w_axes_n = w_axes / w_sum


# -------------------------
# RANK QUERY
# -------------------------
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

    "hardPayload": bool(hard_payload),
    "hardReach": bool(hard_reach),
    "hardPrecision": bool(hard_precision),
    "hardAxes": bool(hard_axes),

    "hardBudget": bool(hard_budget),
    "hardCycle": bool(hard_cycle),
    "hardIP": bool(hard_ip),

    "hardCleanroom": bool(hard_cleanroom),
    "hardESD": bool(hard_esd),
    "hardForce": bool(hard_force),

    "hardType": bool(hard_type),
}

rank_df = run_query(driver, Q_RANK_ROBOTS_FOR_APP, params=params, database=NEO4J_DATABASE)
if rank_df.empty:
    st.warning("No robots returned. Try relaxing constraints or increasing the limit.")
    st.stop()


# -------------------------
# SUMMARY CARDS
# -------------------------
col1, col2, col3, spacer = st.columns([1, 1, 5, 10])

with col1:
    st.metric("Robots shown", int(len(rank_df)))

with col2:
    fully_count = int(rank_df["fullySuitable"].sum()) if "fullySuitable" in rank_df.columns else 0
    st.metric("Fully suitable", fully_count)

with col3:
    st.metric("Relaxation", f"P{relax_payload_pct}% / R{relax_reach_pct}% / Rep{relax_precision_pct}%")


# -------------------------
# TOP 3 (decorate)
# -------------------------
st.subheader("Top 3 Recommended Robots")
top3 = rank_df.head(3)
for i, (_, row) in enumerate(top3.iterrows()):
    render_robot_card(row, i, app_row=app_row, decorate_top3=True)


# -------------------------
# TABLE
# -------------------------
st.subheader("Ranked robot shortlist")

preferred_cols = [
    "distanceScore",
    "fullySuitable",
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
]
cols = [c for c in preferred_cols if c in rank_df.columns]
st.dataframe(rank_df[cols], use_container_width=True, hide_index=True)


# -------------------------
# DOWNLOAD
# -------------------------
csv_bytes = rank_df[cols].to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download results as CSV",
    data=csv_bytes,
    file_name=f"robot_ranking_{selected_app_id}.csv",
    mime="text/csv",
)


# -------------------------
# VISUALS
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

with viz_col3:
    #st.caption("Top robots vs requirements (normalised)")
    fig = _build_radar_for_topN(rank_df, N=3)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough data to draw radar chart.")

best = rank_df.iloc[0]

st.info(f"""
Top robot: {best['robot']}

Reasons:
• Fit score: {best['fitScoreRaw']:.1f}%
• Payload margin: {best['payloadKg'] - best['reqPayloadMinKg']:.2f} kg
• Reach margin: {best['reachMm'] - best['reqReachMinMm']:.0f} mm
• Repeatability margin: {best['reqRepeatabilityMaxMm'] - best['repeatabilityMm']:.3f} mm
""")