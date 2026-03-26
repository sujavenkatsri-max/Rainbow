"""
crash_rate_panel.py — Panel 2: STB Crash Rate Tracker.

render_crash_panel(filters: FilterState) -> None
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

import config
from storage.metrics_store import query_metrics

_CRR_CODES = config.CODES_BY_METRIC_TYPE["crash_rate"]
_CRR_OPTIONS = [f"{c} — {config.CODE_DESCRIPTIONS[c]}" for c in _CRR_CODES]
_CRR_OPTION_MAP = {f"{c} — {config.CODE_DESCRIPTIONS[c]}": c for c in _CRR_CODES}

_COLORS = {
    "CRR_3001": "#8b5cf6",
    "CRR_3002": "#a78bfa",
    "CRR_3003": "#6366f1",
    "CRR_3004": "#818cf8",
    "CRR_3005": "#c084fc",
    "CRR_3006": "#ef4444",  # always red
    "CRR_3007": "#e879f9",
    "CRR_3008": "#f0abfc",
}


def detect_crash_storm(df: pd.DataFrame) -> bool:
    """Return True if crash rate in last 30 min exceeds 2× baseline.

    Parameters:
        df: DataFrame with columns timestamp (datetime), event_count.
            Safe (internal data from DB, not user-supplied).
    """
    try:
        now = datetime.now()
        cutoff = now - timedelta(minutes=30)
        cutoff_str = cutoff.isoformat()

        recent_total = df[df["timestamp"] >= pd.Timestamp(cutoff)]["event_count"].sum()
        baseline_mean = df[df["timestamp"] < pd.Timestamp(cutoff)]["event_count"].mean()

        if pd.isna(baseline_mean) or baseline_mean == 0:
            return False
        return recent_total > baseline_mean * config.CRASH_STORM_MULTIPLIER
    except Exception:
        return False


def render_crash_panel(filters) -> None:
    """Render Panel 2: STB Crash Rate Tracker.

    Parameters:
        filters: FilterState — contains platform_sql_list() and get_time_bounds().
    """
    st.subheader("💥 Panel 2 — STB Crash Rate Tracker")

    # ── Inline filter row ────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 0.8, 1])

    with col1:
        if "panel2_codes" not in st.session_state:
            st.session_state["panel2_codes"] = _CRR_OPTIONS[:]
        selected_labels = st.multiselect(
            "Crash Codes",
            options=_CRR_OPTIONS,
            default=st.session_state["panel2_codes"],
            key="panel2_codes_widget",
            label_visibility="collapsed",
        )

    with col2:
        if st.button("All", key="p2_all"):
            st.session_state["panel2_codes"] = _CRR_OPTIONS[:]
            st.rerun()
        if st.button("None", key="p2_none"):
            st.session_state["panel2_codes"] = []
            st.rerun()

    with col3:
        agg_mode = st.radio(
            "Show as",
            options=["rate_per_1000", "stb_count"],
            key="panel2_agg",
            horizontal=True,
        )

    st.session_state["panel2_codes"] = selected_labels
    selected_codes = [_CRR_OPTION_MAP[lbl] for lbl in selected_labels
                      if lbl in _CRR_OPTION_MAP]

    if not selected_codes:
        st.info("No data for selected filters — try adjusting platform or time range")
        return

    # ── Query ────────────────────────────────────────────────────────────
    try:
        platforms = filters.platform_sql_list()
        start_dt, end_dt = filters.get_time_bounds()
        rows = query_metrics(
            "crash_rate", platforms, selected_codes,
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

    # ── Crash storm detection ─────────────────────────────────────────────
    if detect_crash_storm(df):
        st.warning("⚠️ Crash Storm Detected — total crash rate exceeds 2× baseline in last 30 min")

    # ── Stacked bar + total line chart ────────────────────────────────────
    y_col = agg_mode
    fig = go.Figure()

    totals_by_ts = df.groupby("timestamp", as_index=False)[y_col].sum()
    totals_by_ts = totals_by_ts.sort_values("timestamp")

    for code in selected_codes:
        sub = df[df["code"] == code].sort_values("timestamp")
        if sub.empty:
            continue
        sub = sub.groupby("timestamp", as_index=False).agg({y_col: "mean"})
        fig.add_trace(go.Bar(
            x=sub["timestamp"],
            y=sub[y_col],
            name=code,
            marker_color=_COLORS.get(code, "#888888"),
        ))

    # Total overlay on secondary Y
    fig.add_trace(go.Scatter(
        x=totals_by_ts["timestamp"],
        y=totals_by_ts[y_col],
        name="Total",
        line=dict(color="#1e293b", width=2, dash="dot"),
        yaxis="y2",
    ))

    fig.update_layout(
        barmode="stack",
        height=350,
        margin=dict(l=40, r=60, t=10, b=40),
        yaxis_title=y_col.replace("_", " "),
        yaxis2=dict(overlaying="y", side="right", title="Total"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Top 3 crash codes summary ─────────────────────────────────────────
    top3 = (
        df.groupby("code")["event_count"]
        .sum()
        .sort_values(ascending=False)
        .head(3)
    )
    if not top3.empty:
        st.markdown("**Top crash codes (by event count):**")
        metric_cols = st.columns(len(top3))
        for i, (code, count) in enumerate(top3.items()):
            with metric_cols[i]:
                st.metric(label=code, value=f"{int(count):,}",
                          help=config.CODE_DESCRIPTIONS.get(code, ""))
