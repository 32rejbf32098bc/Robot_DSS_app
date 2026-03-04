# utils_format.py
from __future__ import annotations

from typing import Optional, Tuple
import pandas as pd


def fmt_fit_score(score: float, fully_suitable: bool) -> str:
    score = float(score)
    if fully_suitable and abs(score - 100.0) < 1e-9:
        return "100.0%"
    score = min(score, 99.9)
    return f"{score:.1f}%"


def fmt_range(vmin, vmax, unit=""):
    if pd.isna(vmin) and pd.isna(vmax):
        return "—"
    if pd.isna(vmin):
        return f"≤ {vmax}{unit}".strip()
    if pd.isna(vmax):
        return f"≥ {vmin}{unit}".strip()
    return f"{vmin}–{vmax}{unit}".strip()


def to_float(x) -> Optional[float]:
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


def to_int(x) -> Optional[int]:
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


def truthy(x) -> bool:
    s = str(x).strip().lower()
    return s in ["true", "yes", "y", "1", "required", "req"]


def norm_req_text(x) -> str:
    if x is None:
        return ""
    return str(x).strip().lower()


def req_mode(x) -> str:
    s = norm_req_text(x)
    if s == "":
        return "unknown"
    if "optional" in s:
        return "optional"
    if s in ["no", "false", "0"]:
        return "not_required"
    if s in ["yes", "true", "1", "required"]:
        return "required"
    # if the field is ISO-like ("iso 7"), treat as required
    if any(ch.isdigit() for ch in s):
        return "required"
    return "required"


def delta_span(delta_text: str, status: str) -> str:
    """
    status:
      - good: green
      - bad: red
      - warn: amber (needs info / caution)
      - info: blue (neutral info)
      - eq: neutral grey
    """
    if status == "good":
        color = "rgba(76, 175, 80, 1)"
    elif status == "bad":
        color = "rgba(239, 83, 80, 1)"
    elif status == "warn":
        color = "rgba(245, 158, 11, 1)"  # amber
    elif status == "info":
        color = "rgba(96, 165, 250, 1)"  # light blue
    else:
        color = "rgba(255,255,255,0.70)"
    return f"""<span style="color:{color}; font-weight:600;">({delta_text})</span>"""


def fmt_delta(x: float, unit: str = "") -> str:
    if x is None:
        return "Δ —"
    if abs(x) < 1e-12:
        return f"Δ 0{unit}".strip()
    sign = "+" if x > 0 else ""
    return f"Δ {sign}{x:g}{unit}".strip()


def compare_upper_bound_lower_is_better(r_val: Optional[float], req_max: Optional[float], unit: str) -> Tuple[str, str]:
    if r_val is None or req_max is None:
        return "—", delta_span("Δ —", "eq")
    d = r_val - req_max
    if d > 0:
        return f"{r_val:g}{unit}", delta_span(fmt_delta(d, unit), "bad")
    if d < 0:
        return f"{r_val:g}{unit}", delta_span(fmt_delta(d, unit), "good")
    return f"{r_val:g}{unit}", delta_span("Δ 0", "eq")


def compare_min_bound_higher_is_better(r_val: Optional[float], req_min: Optional[float], unit: str) -> Tuple[str, str]:
    if r_val is None or req_min is None:
        return "—", delta_span("Δ —", "eq")
    d = r_val - req_min
    if d < 0:
        return f"{r_val:g}{unit}", delta_span(fmt_delta(d, unit), "bad")
    if d > 0:
        return f"{r_val:g}{unit}", delta_span(fmt_delta(d, unit), "good")
    return f"{r_val:g}{unit}", delta_span("Δ 0", "eq")


def compare_budget_overlap(cost_min: Optional[float], cost_max: Optional[float], a_min: Optional[float], a_max: Optional[float]) -> Tuple[str, str]:
    """
    - In range (overlap): GOOD (green)
    - Too expensive: BAD (red)
    - Too cheap (below range): WARN (amber) rather than bad (can still be acceptable but needs checks)
    """
    if cost_min is None or cost_max is None or a_min is None or a_max is None:
        return "—", delta_span("Δ —", "eq")

    overlap = (cost_min <= a_max) and (cost_max >= a_min)
    if overlap:
        return f"{cost_min:g}–{cost_max:g} USD", delta_span("in range", "good")

    if cost_min > a_max:
        d = cost_min - a_max
        return f"{cost_min:g}–{cost_max:g} USD", delta_span(fmt_delta(d, " USD"), "bad")

    if cost_max < a_min:
        d = cost_max - a_min
        return f"{cost_min:g}–{cost_max:g} USD", delta_span(fmt_delta(d, " USD"), "warn")

    return f"{cost_min:g}–{cost_max:g} USD", delta_span("Δ —", "eq")


def compare_feature_req(robot_val, app_req_val) -> Tuple[str, str]:
    """
    Generic yes/no/optional feature comparison:
      - If app doesn't require => INFO
      - If app requires:
          - robot yes/true => GOOD
          - robot optional => WARN (available but confirm/configure)
          - robot no/false/blank => BAD
    """
    mode = req_mode(app_req_val)

    rv_raw = "" if robot_val is None else str(robot_val)
    rv = "—" if rv_raw.strip() == "" else rv_raw
    rv_norm = rv_raw.strip().lower()

    # App does not require (or is optional/unknown) -> feature doesn't matter for suitability
    if mode in ["optional", "not_required", "unknown"]:
        return rv, delta_span("Not required", "info")

    # App requires it:
    if rv_norm == "" or rv_norm in ["no", "false", "0", "none", "na", "n/a", "-"]:
        return rv, delta_span("Missing", "bad")

    if "optional" in rv_norm or rv_norm in ["option", "maybe", "available", "addon", "add-on"]:
        return rv, delta_span("Optional (confirm)", "warn")

    ok = truthy(robot_val)
    return rv, delta_span("Meets" if ok else "Missing", "good" if ok else "bad")


def compare_type(robot_type: str, app_type_req) -> Tuple[str, str]:
    rt = (robot_type or "").strip()
    at = "" if app_type_req is None else str(app_type_req).strip()
    if at == "":
        return rt if rt else "—", delta_span("Not specified", "info")
    ok = rt.lower() in at.lower() or at.lower() in rt.lower()
    return rt if rt else "—", delta_span("Matches" if ok else "Mismatch", "good" if ok else "bad")


def compare_cleanroom_iso(
    app_iso_req: Optional[int],
    robot_iso: Optional[int],
    cleanroom_needs_info: bool,
    robot_raw: Optional[str] = None,
) -> Tuple[str, str]:
    """
    app_iso_req:
      - None => not required
      - 999  => required but ISO not specified
      - 1..9 => ISO class requirement (lower is cleaner/better)
    robot_iso:
      - None => no cleanroom
      - 999  => "yes/optional" but ISO unknown
      - 1..9 => ISO class capability
    """
    raw = "—" if robot_raw is None else str(robot_raw)

    # Not required
    if app_iso_req is None:
        return raw, delta_span("Not required", "info")

    # App requires cleanroom but didn't state ISO
    if app_iso_req == 999:
        if robot_iso is None:
            return raw, delta_span("Missing", "bad")
        # robot has something, but you need to specify ISO class target
        return raw, delta_span("Specify ISO class", "warn")

    # App specifies ISO N
    # Robot has none
    if robot_iso is None:
        return raw, delta_span("Missing", "bad")

    # Robot says yes but doesn't provide ISO
    if robot_iso == 999:
        return raw, delta_span("Confirm ISO class", "warn")

    # Both numeric
    if robot_iso <= app_iso_req:
        # Cleaner than required is fine; treat as good
        if robot_iso < app_iso_req:
            return raw, delta_span(f"Meets (ISO {robot_iso} < {app_iso_req})", "good")
        return raw, delta_span("Meets", "good")

    # Worse (higher ISO number) than required
    return raw, delta_span(f"ISO {robot_iso} > {app_iso_req}", "bad")