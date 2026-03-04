# charts.py
from __future__ import annotations

from typing import Optional
import pandas as pd
import plotly.graph_objects as go


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