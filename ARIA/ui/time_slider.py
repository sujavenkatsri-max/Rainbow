"""
time_slider.py — Dual-handle and point time slider components for KPI Analyzer.
"""
import streamlit as st
from datetime import datetime, timedelta
from typing import Tuple, List, Optional

from storage.metrics_store import get_available_time_range
from ingest.metric_generator import snap_to_5min


def _build_timestamp_options(start_iso: str, end_iso: str) -> List[str]:
    """Build a list of 5-min-snapped timestamp strings between start and end.

    Returns: list of ISO 8601 strings.
    Parameters are safe (internal DB values, not user-supplied).
    """
    from dateutil.parser import parse as parse_dt
    options = []
    current = snap_to_5min(parse_dt(start_iso))
    end_dt  = snap_to_5min(parse_dt(end_iso))
    while current <= end_dt:
        options.append(current.isoformat())
        current += timedelta(minutes=5)
    return options


def render_window_sliders(key_prefix: str) -> Tuple[Optional[str], Optional[str],
                                                     Optional[str], Optional[str]]:
    """Render dual range sliders for Window A and Window B.

    Returns: (window_a_start, window_a_end, window_b_start, window_b_end)
             as ISO 8601 strings, or (None, None, None, None) if unavailable.
    """
    try:
        db_start, db_end = get_available_time_range()
        options = _build_timestamp_options(db_start, db_end)

        if len(options) < 4:
            st.warning("Not enough data for window comparison.")
            return None, None, None, None

        mid_idx = len(options) // 2

        st.markdown("**Window A (baseline)**")
        wa_range = st.select_slider(
            "Window A",
            options=options,
            value=(options[0], options[mid_idx - 1]),
            key=f"{key_prefix}_wa",
            label_visibility="collapsed",
        )

        st.markdown("**Window B (comparison)**")
        wb_range = st.select_slider(
            "Window B",
            options=options,
            value=(options[mid_idx], options[-1]),
            key=f"{key_prefix}_wb",
            label_visibility="collapsed",
        )

        # Overlap validation
        if wa_range[1] >= wb_range[0]:
            st.error("Windows must not overlap. Window B must start after Window A ends.")
            return None, None, None, None

        return wa_range[0], wa_range[1], wb_range[0], wb_range[1]

    except Exception as exc:
        st.error(f"Slider unavailable: {exc}")
        return None, None, None, None


def render_point_sliders(key_prefix: str) -> Tuple[Optional[str], Optional[str]]:
    """Render two single-value (point) sliders for Point-vs-Point comparison.

    Returns: (point_a, point_b) as ISO 8601 strings.
    """
    try:
        db_start, db_end = get_available_time_range()
        options = _build_timestamp_options(db_start, db_end)

        if len(options) < 2:
            st.warning("Not enough data.")
            return None, None

        mid_idx = len(options) // 2

        point_a = st.select_slider(
            "Point A",
            options=options,
            value=options[mid_idx // 2],
            key=f"{key_prefix}_pa",
        )
        point_b = st.select_slider(
            "Point B",
            options=options,
            value=options[mid_idx],
            key=f"{key_prefix}_pb",
        )

        if point_a >= point_b:
            st.error("Point A must be before Point B.")
            return None, None

        return point_a, point_b

    except Exception as exc:
        st.error(f"Point slider unavailable: {exc}")
        return None, None
