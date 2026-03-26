"""
dashboard.py — Main layout assembly for ARIA dashboard.
"""
import streamlit as st

from ui.filters import build_filter_state
from panels.error_rate_panel import render_error_panel
from panels.crash_rate_panel import render_crash_panel
from panels.resource_panel import render_resource_panel
from ui.aria_panel import render_aria_panel


def render_kpi_analyzer(filters) -> None:
    """Render the KPI Analyzer / Validator section.

    Parameters:
        filters: FilterState — provides platform_sql_list() for scope.
    """
    from datetime import datetime, timedelta
    from analyzer.kpi_comparator import compare_windows
    from analyzer.report_generator import render_comparison_report
    from ui.time_slider import render_window_sliders, render_point_sliders

    st.markdown("---")
    st.subheader("📊 KPI Analyzer / Validator")

    mode = st.radio(
        "Comparison Mode",
        options=["Window vs Window", "Point vs Point", "Baseline vs Current"],
        horizontal=True,
        key="kpi_mode",
    )

    platform = st.selectbox(
        "Platform scope",
        options=["all"] + __import__("config").PLATFORMS,
        key="kpi_platform",
    )
    scope = st.selectbox(
        "Metric type",
        options=["all", "error_rate", "crash_rate", "cpu_utilization", "memory_utilization"],
        key="kpi_scope",
    )

    wa_start = wa_end = wb_start = wb_end = None

    if mode == "Window vs Window":
        wa_start, wa_end, wb_start, wb_end = render_window_sliders("kpi_wvw")

    elif mode == "Point vs Point":
        pa, pb = render_point_sliders("kpi_pvp")
        if pa and pb:
            from ingest.metric_generator import snap_to_5min
            from dateutil.parser import parse as parse_dt
            wa_start = wa_end = pa
            wb_start = wb_end = pb

    elif mode == "Baseline vs Current":
        now = datetime.now()
        start_dt, end_dt = filters.get_time_bounds()
        wa_start = (now - timedelta(hours=48)).isoformat()
        wa_end   = (now - timedelta(hours=24)).isoformat()
        wb_start = start_dt.isoformat()
        wb_end   = end_dt.isoformat()
        st.caption(f"Baseline: {wa_start[:16]} → {wa_end[:16]}")
        st.caption(f"Current:  {wb_start[:16]} → {wb_end[:16]}")

    run_disabled = not (wa_start and wa_end and wb_start and wb_end)
    if st.button("▶ Run Comparison", disabled=run_disabled, key="kpi_run"):
        with st.spinner("Computing delta..."):
            try:
                df = compare_windows(
                    (wa_start, wa_end),
                    (wb_start, wb_end),
                    scope=scope,
                    platform=platform,
                )
                render_comparison_report(df, (wa_start, wa_end),
                                         (wb_start, wb_end), platform)
            except Exception as exc:
                st.error(f"Comparison failed: {exc}")


def render_dashboard() -> None:
    """Assemble and render the full dashboard layout."""
    filters = build_filter_state()

    render_error_panel(filters)
    st.markdown("---")
    render_crash_panel(filters)
    st.markdown("---")
    render_resource_panel(filters)

    render_kpi_analyzer(filters)
    render_aria_panel()
