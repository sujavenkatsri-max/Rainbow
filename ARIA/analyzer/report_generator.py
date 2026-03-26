"""
report_generator.py — Delta report builder and CSV export for KPI Analyzer.
"""
import math
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from typing import Optional

import config


def _fmt_pct(val) -> str:
    """Format a pct_change float as a display string."""
    if isinstance(val, str):
        return val
    if math.isinf(val):
        return "+inf%"
    return f"{val:+.1f}%"


def _color_rows(row):
    """Apply background color to DataFrame rows based on status."""
    status = row.get("status", "")
    if status == "Degraded":
        return ["background-color: #fde8e8"] * len(row)
    if status == "Improved":
        return ["background-color: #e8fde8"] * len(row)
    return [""] * len(row)


def render_comparison_report(
    df: pd.DataFrame,
    window_a: tuple,
    window_b: tuple,
    platform: str,
) -> None:
    """Render the full KPI comparison report in Streamlit.

    Parameters:
        df: DataFrame from kpi_comparator.compare_windows().
        window_a, window_b: (start, end) tuples — safe internal values.
        platform: display label only, not SQL-injected here.
    """
    if df.empty:
        st.info("No data available for the selected windows.")
        return

    # ── Summary banner ────────────────────────────────────────────────────
    counts = df["status"].value_counts().to_dict()
    degraded = counts.get("Degraded", 0)
    improved = counts.get("Improved", 0)
    stable   = counts.get("Stable",   0)

    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Degraded",  degraded)
    c2.metric("🟢 Improved",  improved)
    c3.metric("⚪ Stable",    stable)

    # ── Delta table ────────────────────────────────────────────────────────
    display_df = df.copy()
    display_df["pct_change"] = display_df["pct_change"].apply(_fmt_pct)
    display_df["value_a"]    = display_df["value_a"].round(3)
    display_df["value_b"]    = display_df["value_b"].round(3)
    display_df["delta"]      = display_df["delta"].round(3)

    try:
        styled = display_df.style.apply(_color_rows, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Top Movers ────────────────────────────────────────────────────────
    st.markdown("**Top Movers**")
    top_degraded = df[df["status"] == "Degraded"].head(3)
    top_improved = df[df["status"] == "Improved"].head(3)

    if not top_degraded.empty or not top_improved.empty:
        col_deg, col_imp = st.columns(2)
        with col_deg:
            st.markdown("*Most Degraded*")
            for _, row in top_degraded.iterrows():
                pct_display = _fmt_pct(row["pct_change"])
                st.metric(
                    label=f"{row['code']} [{row['platform']}]",
                    value=f"{row['value_b']:.2f}",
                    delta=pct_display,
                    delta_color="inverse",
                )
        with col_imp:
            st.markdown("*Most Improved*")
            for _, row in top_improved.iterrows():
                pct_display = _fmt_pct(row["pct_change"])
                st.metric(
                    label=f"{row['code']} [{row['platform']}]",
                    value=f"{row['value_b']:.2f}",
                    delta=pct_display,
                )

    # ── Platform heatmap (only when all platforms) ─────────────────────────
    if platform == "all" and "platform" in df.columns:
        st.markdown("**Platform Heatmap (% Change)**")
        try:
            pivot = df.pivot_table(
                index="code", columns="platform",
                values="pct_change",
                aggfunc="mean",
            ).fillna(0)

            # Replace inf with large sentinel for display
            pivot = pivot.applymap(lambda x: 999.0 if math.isinf(x) else x)

            heatmap = go.Figure(go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale="RdYlGn_r",
                zmid=0,
                text=pivot.applymap(lambda x: f"{x:+.1f}%").values,
                texttemplate="%{text}",
            ))
            heatmap.update_layout(height=400, margin=dict(l=120, r=20, t=20, b=40))
            st.plotly_chart(heatmap, use_container_width=True)
        except Exception as exc:
            st.caption(f"Heatmap unavailable: {exc}")

    # ── Export ─────────────────────────────────────────────────────────────
    export_df = display_df.copy()
    csv_data = export_df.to_csv(index=False)
    wa_start = window_a[0][:10] if window_a else "wa"
    wb_start = window_b[0][:10] if window_b else "wb"
    st.download_button(
        label="📥 Download CSV",
        data=csv_data,
        file_name=f"stb_kpi_{wa_start}_vs_{wb_start}.csv",
        mime="text/csv",
    )
