"""
app.py — ARIA STB KPI Analyzer — Streamlit entrypoint.

Startup sequence:
1. init_db()
2. Seed if needed (blocking, with spinner)
3. Start background engine (once, guarded by session_state)
4. Render dashboard
"""
# ── DB must be initialized first, before any other import-time side effects ──
from storage.db_init import init_db
init_db()

import streamlit as st

st.set_page_config(
    page_title="ARIA — STB KPI Analyzer",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from storage.metrics_store import is_seeded
from ingest import seed_data
from ingest import anomaly_injector
from ingest import scheduler
from ui.dashboard import render_dashboard


def main() -> None:
    st.title("📡 ARIA — STB KPI Monitoring & Agentic Analysis")
    st.caption(
        "Automated Root-cause & Insights Analyst · "
        "Data refreshes every 10s (DEMO MODE)"
    )

    # ── Step 2: Seed on first launch ──────────────────────────────────────
    if not is_seeded():
        with st.spinner("⏳ Seeding 24h of historical data — this takes ~15 seconds..."):
            seed_data.run_seed()
        st.success("✅ Historical data ready.")
        st.rerun()

    # ── Step 3: Start background engine (once per process) ───────────────
    if "scheduler_started" not in st.session_state:
        scheduler.start_background_engine()
        st.session_state["scheduler_started"] = True

    # ── Step 4: Render dashboard ─────────────────────────────────────────
    render_dashboard()


if __name__ == "__main__":
    main()
else:
    # Streamlit runs the module at import — call main() directly
    main()
