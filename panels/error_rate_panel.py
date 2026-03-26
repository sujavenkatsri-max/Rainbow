"""
error_rate_panel.py — Panel 1: STB Error Rate Monitor.

render_error_panel(filters: FilterState) -> None
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

import config
from storage.metrics_store import query_metrics

# Color palette by category (index-stable — not random)
_COLORS = {
    "ERR_2001": "#3b82f6",
    "ERR_2002": "#60a5fa",
    "ERR_2003": "#ef4444",
    "ERR_2004": "#f87171",
    "ERR_2005": "#f97316",
    "ERR_2006": "#fb923c",
    "ERR_2007": "#fdba74",
    "ERR_2008": "#fed7aa",
}

_ERR_CODES = config.CODES_BY_METRIC_TYPE["error_rate"]
_ERR_OPTIONS = [f"{c} — {config.CODE_DESCRIPTIONS[c]}" for c in _ERR_CODES]
_ERR_OPTION_MAP = {f"{c} — {config.CODE_DESCRIPTIONS[c]}": c for c in _ERR_CODES}


def render_error_panel(filters) -> None:
    """Render Panel 1: STB Error Rate Monitor.

    Parameters:
        filters: FilterState — contains platform_sql_list() and get_time_bounds().
                 Safe; not SQL-injected here (delegated to metrics_store).
    """
    st.subheader("📡 Panel 1 — STB Error Rate Monitor")

    # ── Inline filter row ────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 0.8, 1])

    with col1:
        # Default: all ERR codes selected
        if "panel1_codes" not in st.session_state:
            st.session_state["panel1_codes"] = _ERR_OPTIONS[:]
        selected_labels = st.multiselect(
            "Error Codes",
            options=_ERR_OPTIONS,
            default=st.session_state["panel1_codes"],
            key="panel1_codes_widget",
            label_visibility="collapsed",
        )

    with col2:
        if st.button("All", key="p1_all"):
            st.session_state["panel1_codes"] = _ERR_OPTIONS[:]
            st.rerun()
        if st.button("None", key="p1_none"):
            st.session_state["panel1_codes"] = []
            st.rerun()

    with col3:
        agg_mode = st.radio(
            "Show as",
            options=["rate_per_1000", "stb_count"],
            key="panel1_agg",
            horizontal=True,
        )

    # Sync widget value back to session state
    st.session_state["panel1_codes"] = selected_labels
    selected_codes = [_ERR_OPTION_MAP[lbl] for lbl in selected_labels
                      if lbl in _ERR_OPTION_MAP]

    if not selected_codes:
        st.info("No data for selected filters — try adjusting platform or time range")
        return

    # ── Query ────────────────────────────────────────────────────────────
    try:
        platforms = filters.platform_sql_list()
        start_dt, end_dt = filters.get_time_bounds()
        rows = query_metrics(
            "error_rate", platforms, selected_codes,
            start_dt.isoformat(), end_dt.isoformat(),
        )
    except Exception as exc:
        st.error(f"Panel unavailable: {exc}")
        return

    if not rows:
        st.info("No data for selected filters — try adjusting platform or time range")
        return

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # ── Chart ────────────────────────────────────────────────────────────
    fig = go.Figure()
    y_col = agg_mode  # "rate_per_1000" or "stb_count"

    for code in selected_codes:
        sub = df[df["code"] == code].sort_values("timestamp")
        if sub.empty:
            continue
        # Aggregate across platforms if multiple
        sub = sub.groupby("timestamp", as_index=False).agg(
            {y_col: "mean", "event_count": "sum", "stb_count": "sum",
             "rate_per_1000": "mean"}
        )
        fig.add_trace(go.Scatter(
            x=sub["timestamp"],
            y=sub[y_col],
            mode="lines+markers",
            name=f"{code}",
            line=dict(color=_COLORS.get(code, "#888888"), width=2),
            marker=dict(size=4),
        ))

    fig.update_layout(
        height=350,
        margin=dict(l=40, r=10, t=10, b=40),
        yaxis_title=y_col.replace("_", " "),
        xaxis_title="Time",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Summary table ────────────────────────────────────────────────────
    _render_summary_table(df, selected_codes)


def _render_summary_table(df: pd.DataFrame, codes: list) -> None:
    """Render latest window values with delta vs previous window."""
    try:
        timestamps = sorted(df["timestamp"].unique())
        if len(timestamps) < 2:
            return

        latest_ts = timestamps[-1]
        prev_ts   = timestamps[-2]

        rows_out = []
        for code in codes:
            latest_row = df[(df["code"] == code) & (df["timestamp"] == latest_ts)]
            prev_row   = df[(df["code"] == code) & (df["timestamp"] == prev_ts)]

            if latest_row.empty:
                continue

            latest_val = latest_row["rate_per_1000"].mean()
            prev_val   = prev_row["rate_per_1000"].mean() if not prev_row.empty else latest_val
            delta      = latest_val - prev_val
            direction  = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")

            rows_out.append({
                "Code":           code,
                "Description":    config.CODE_DESCRIPTIONS.get(code, ""),
                "Latest /1k":     f"{latest_val:.2f}",
                "Prev /1k":       f"{prev_val:.2f}",
                "Delta":          f"{delta:+.2f}",
                "Dir":            direction,
            })

        if rows_out:
            st.dataframe(pd.DataFrame(rows_out), use_container_width=True, hide_index=True)
    except Exception as exc:
        print(f"[error_rate_panel] summary table error: {exc}")
