# components.py
from __future__ import annotations

from typing import Optional
import streamlit as st

from utils_format import (
    fmt_fit_score, fmt_range,
    to_float, to_int,
    compare_upper_bound_lower_is_better,
    compare_min_bound_higher_is_better,
    compare_budget_overlap,
    compare_feature_req,
    compare_type,
    compare_cleanroom_iso,
)


def render_robot_card(row, rank_idx: int, app_row: Optional[dict] = None, decorate_top3: bool = False):
    fully = bool(row.get("fullySuitable", False))
    overspec_any = bool(row.get("suitableButOverspecced", False))

    score = float(row.get("fitScoreRaw", 0.0)) if "fitScoreRaw" in row else (
        100.0 * (1.0 - float(row.get("distanceScore", 0.0)))
    )

    score_txt = fmt_fit_score(score, fully)

    # -------------------------
    # Badge / colour logic
    # IMPORTANT: overspec FIRST
    # -------------------------
    if overspec_any:
        bg = "rgba(30,58,138,0.06)"
        border = "rgba(160,190,255,0.65)"
        badge = "🟦 Suitable but over-specced"
    elif fully:
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

    # Existing display strings (from query)
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

    # NEW extra robot-only fields (formatted strings from query)
    weight_txt = row.get("weight", "—")
    mounting_txt = row.get("mounting", "—")
    speed_grade_txt = row.get("speedGrade", "—")
    app_suit_txt = row.get("applicationSuitability", "—")
    safety_feat_txt = row.get("safetyFeature", "—")
    prog_complex_txt = row.get("programmingComplexity", "—")

    # If Top-3 decoration enabled, we override some fields with delta displays
    if decorate_top3 and app_row is not None:
        r_payload = to_float(row.get("payloadKg"))
        r_reach = to_float(row.get("reachMm"))
        r_rep = to_float(row.get("repeatabilityMm"))
        r_axes = to_int(row.get("axis"))
        r_cycle = to_float(row.get("cycleTimeSec"))

        r_ip_num = to_int(row.get("ipRatingNum"))
        r_clean_raw = row.get("cleanroomOptionRaw", None)
        r_esd_raw = row.get("esdSafeRaw", None)
        r_force_raw = row.get("forceSensingRaw", None)
        r_type_raw = row.get("robotType", "")

        cost_min = to_float(row.get("costMin"))
        cost_max = to_float(row.get("costMax"))

        a_pmin = to_float(app_row.get("payloadMinKg"))
        a_rmin = to_float(app_row.get("reachMinMm"))
        a_rep_req = to_float(app_row.get("repeatabilityRequiredMm"))
        a_axes_min = to_int(app_row.get("axesMin"))
        a_cycle_req = to_float(app_row.get("cycleTimeTargetSec"))
        a_budget_min = to_float(app_row.get("budgetMinUsd"))
        a_budget_max = to_float(app_row.get("budgetMaxUsd"))

        a_ip_req = to_int(row.get("reqIpRatingNum"))

        a_clean_req = app_row.get("cleanroomRequired")
        a_esd_req = app_row.get("esdProtection")
        a_force_req = app_row.get("forceSensingRequired")
        a_type_req = app_row.get("typicalRobotType")

        # NOTE: display deltas currently use MIN bounds for payload/reach (overspec is fine)
        p_val, p_delta = compare_min_bound_higher_is_better(r_payload, a_pmin, " kg")
        payload_txt = f"{p_val} {p_delta}"

        r_val, r_delta = compare_min_bound_higher_is_better(r_reach, a_rmin, " mm")
        reach_txt = f"{r_val} {r_delta}"

        rep_val, rep_delta = compare_upper_bound_lower_is_better(r_rep, a_rep_req, " mm")
        precision_txt = f"{rep_val} {rep_delta}"

        ax_val, ax_delta = compare_min_bound_higher_is_better(
            float(r_axes) if r_axes is not None else None,
            float(a_axes_min) if a_axes_min is not None else None,
            ""
        )
        axes_txt = f"{ax_val} {ax_delta}"

        b_val, b_delta = compare_budget_overlap(cost_min, cost_max, a_budget_min, a_budget_max)
        budget_txt = f"{b_val} {b_delta}" if b_val != "—" else (row.get("budget") or "—")

        cy_val, cy_delta = compare_upper_bound_lower_is_better(r_cycle, a_cycle_req, " s")
        cycle_txt = f"{cy_val} {cy_delta}"

        if r_ip_num is None or a_ip_req is None:
            ip_txt = "—"
        else:
            d = r_ip_num - a_ip_req
            status = "bad" if d < 0 else ("good" if d > 0 else "eq")
            from utils_format import delta_span, fmt_delta
            ip_txt = f"IP{r_ip_num} {delta_span(fmt_delta(d,'' ) if status!='eq' else 'Δ 0', status)}"

        app_iso_req = to_int(row.get("reqCleanroomIsoParsed"))
        robot_iso = to_int(row.get("robotCleanroomIsoParsed"))
        needs_info = bool(row.get("cleanroomNeedsInfo", False))

        cl_val, cl_delta = compare_cleanroom_iso(
            app_iso_req=app_iso_req,
            robot_iso=robot_iso,
            cleanroom_needs_info=needs_info,
            robot_raw=r_clean_raw,
        )
        cleanroom_txt = f"{cl_val} {cl_delta}"

        esd_val, esd_delta = compare_feature_req(r_esd_raw, a_esd_req)
        esd_txt = f"{esd_val} {esd_delta}"

        fo_val, fo_delta = compare_feature_req(r_force_raw, a_force_req)
        force_txt = f"{fo_val} {fo_delta}"

        ty_val, ty_delta = compare_type(str(r_type_raw), a_type_req)
        type_match_txt = f"{ty_val} {ty_delta}"

        # The new robot-only fields stay as their plain formatted strings (no app target to compare)

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
            <div>Weight</div><div>{weight_txt}</div>
            <div>Mounting</div><div>{mounting_txt}</div>
            <div>Speed grade</div><div>{speed_grade_txt}</div>
            <div>App suitability</div><div>{app_suit_txt}</div>
            <div>Safety feature</div><div>{safety_feat_txt}</div>
            <div>Programming complexity</div><div>{prog_complex_txt}</div>
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

    payload_req = fmt_range(app_row.get("payloadMinKg"), app_row.get("payloadMaxKg"), " kg")
    reach_req = fmt_range(app_row.get("reachMinMm"), app_row.get("reachMaxMm"), " mm")

    rep_req = app_row.get("repeatabilityRequiredMm")
    rep_txt = "—" if rep_req is None else f"≤ {rep_req} mm"

    axes_min = app_row.get("axesMin")
    axes_txt = "—" if axes_min is None else f"≥ {int(axes_min)}"

    budget_txt = fmt_range(app_row.get("budgetMinUsd"), app_row.get("budgetMaxUsd"), " USD")

    ct = app_row.get("cycleTimeTargetSec")
    cycle_txt = "—" if ct is None else f"≤ {ct} s"

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