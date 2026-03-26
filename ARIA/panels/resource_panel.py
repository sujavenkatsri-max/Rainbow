"""
resource_panel.py — Panel 3: Device Resource Utilization.

render_resource_panel(filters: FilterState) -> None
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta

import config
from storage.metrics_store import query_metrics

_CPU_CODES = config.CODES_BY_METRIC_TYPE["cpu_utilization"]
_MEM_CODES = config.CODES_BY_METRIC_TYPE["memory_utilization"]
_ALL_RESOURCE_CODES = _CPU_CODES + _MEM_CODES

_RESOURCE_COLORS = {
    "CPU_AVG":          "#3b82f6",
    "CPU_P95":          "#93c5fd",
    "MEM_FREE_AVG":     "#10b981",
    "MEM_HEAP_USED":    "#f59e0b",
    "MEM_SWAP_USED":    "#f97316",
    "THERMAL_THROTTLE": "#ef4444",
}


def render_resource_panel(filters) -> None:
    """Render Panel 3: Device Resource Utilization.

    Parameters:
        filters: FilterState — contains platform_sql_list() and get_time_bounds().
    """
    st.subheader("🖥️ Panel 3 — Device Resource Utilization")

    # ── Inline filter row ────────────────────────────────────────────────
    if "panel3_metrics" not in st.session_state:
        st.session_state["panel3_metrics"] = ["CPU_AVG", "MEM_FREE_AVG"]

    selected_metrics = st.multiselect(
        "Resource Metrics",
        options=_ALL_RESOURCE_CODES,
        default=st.session_state["panel3_metrics"],
        key="panel3_metrics_widget",
        format_func=lambda c: f"{c} — {config.CODE_DESCRIPTIONS.get(c, c)}",
    )
    st.session_state["panel3_metrics"] = selected_metrics

    if not selected_metrics:
        st.info("No data for selected filters — try adjusting platform or time range")
        return

    # ── Query ────────────────────────────────────────────────────────────
    try:
        platforms = filters.platform_sql_list()
        start_dt, end_dt = filters.get_time_bounds()

        # Query cpu and memory separately
        cpu_sel = [c for c in selected_metrics if c in _CPU_CODES]
        mem_sel = [c for c in selected_metrics if c in _MEM_CODES]

        all_rows = []
        if cpu_sel:
            all_rows += query_metrics("cpu_utilization", platforms, cpu_sel,
                                      start_dt.isoformat(), end_dt.isoformat())
        if mem_sel:
            all_rows += query_metrics("memory_utilization", platforms, mem_sel,
                                      start_dt.isoformat(), end_dt.isoformat())
    except Exception as exc:
        st.error(f"Panel unavailable: {exc}")
        return

    if not all_rows:
        st.info("No data for selected filters — try adjusting platform or time range")
        return

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # ── Dual-axis chart ───────────────────────────────────────────────────
    fig = go.Figure()

    has_cpu = any(c in _CPU_CODES for c in selected_metrics)
    has_mem = any(c in _MEM_CODES for c in selected_metrics)

    for code in selected_metrics:
        sub = df[df["code"] == code].sort_values("timestamp")
        if sub.empty:
            continue
        sub = sub.groupby("timestamp", as_index=False).agg({"rate_per_1000": "mean"})

        is_cpu = code in _CPU_CODES
        yaxis  = "y" if is_cpu else "y2"
        dash   = "dash" if code == "CPU_P95" else "solid"

        fig.add_trace(go.Scatter(
            x=sub["timestamp"],
            y=sub["rate_per_1000"],
            mode="lines",
            name=code,
            line=dict(color=_RESOURCE_COLORS.get(code, "#888888"),
                      width=2, dash=dash),
            yaxis=yaxis,
        ))

    # CPU threshold bands (only when CPU metrics are selected)
    if has_cpu:
        fig.add_hrect(y0=80, y1=90, fillcolor="#f59e0b", opacity=0.08,
                      layer="below", line_width=0)
        fig.add_hrect(y0=90, y1=100, fillcolor="#ef4444", opacity=0.08,
                      layer="below", line_width=0)

    # Thermal throttle vertical shading
    if "THERMAL_THROTTLE" in df["code"].values:
        throttle_df = df[df["code"] == "THERMAL_THROTTLE"].sort_values("timestamp")
        throttle_df = throttle_df.groupby("timestamp", as_index=False).agg(
            {"rate_per_1000": "mean"}
        )
        threshold_val = 100.0
        for _, row in throttle_df.iterrows():
            if row["rate_per_1000"] > threshold_val:
                ts_end = row["timestamp"] + pd.Timedelta(minutes=5)
                fig.add_vrect(
                    x0=row["timestamp"], x1=ts_end,
                    fillcolor="#ef4444", opacity=0.10,
                    layer="below", line_width=0,
                )

    # Memory pressure annotations
    if "MEM_FREE_AVG" in df["code"].values:
        mf_df = df[df["code"] == "MEM_FREE_AVG"].sort_values("timestamp")
        mf_df = mf_df.groupby("timestamp", as_index=False).agg({"rate_per_1000": "mean"})
        low_mem = mf_df[mf_df["rate_per_1000"] < config.MEM_FREE_WARNING_MB]
        for _, row in low_mem.iterrows():
            fig.add_annotation(
                x=row["timestamp"], y=row["rate_per_1000"],
                text="⚠️", showarrow=False, yref="y2",
                font=dict(size=12),
            )

    layout_kwargs = dict(
        height=370,
        margin=dict(l=40, r=60, t=10, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    if has_cpu and has_mem:
        layout_kwargs["yaxis"] = dict(title="CPU (%)", range=[0, 105])
        layout_kwargs["yaxis2"] = dict(
            title="Memory (MB)", overlaying="y", side="right"
        )
    elif has_cpu:
        layout_kwargs["yaxis"] = dict(title="CPU (%)", range=[0, 105])
    elif has_mem:
        # Hide left axis when only memory selected
        layout_kwargs["yaxis"] = dict(visible=False)
        layout_kwargs["yaxis2"] = dict(
            title="Memory (MB)", overlaying="y", side="right"
        )

    fig.update_layout(**layout_kwargs)
    st.plotly_chart(fig, use_container_width=True)
