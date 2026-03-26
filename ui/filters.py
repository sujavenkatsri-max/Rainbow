"""
filters.py — Sidebar global filter components for ARIA dashboard.
"""
import streamlit as st
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import config


@dataclass
class FilterState:
    """Encapsulates all active sidebar filter values."""

    platforms: List[str]
    time_range_label: str
    time_range_hours: int
    custom_start: Optional[datetime]
    custom_end: Optional[datetime]

    def get_time_bounds(self):
        """Return (start_datetime, end_datetime) as timezone-naive datetime objects.

        Returns: tuple[datetime, datetime].
        """
        if (self.time_range_label == "Custom"
                and self.custom_start and self.custom_end):
            return self.custom_start, self.custom_end
        end = datetime.now()
        start = end - timedelta(hours=self.time_range_hours)
        return start, end

    def platform_sql_list(self) -> List[str]:
        """Return list of platform names to use in SQL IN clause.

        Returns: list[str] — always concrete platform names (never 'All').
        """
        if not self.platforms or "All" in self.platforms:
            return config.PLATFORMS
        return self.platforms


_TIME_RANGE_OPTIONS = {
    "Last 1h":  1,
    "Last 3h":  3,
    "Last 6h":  6,
    "Last 12h": 12,
    "Last 24h": 24,
    "Custom":   0,
}


def build_filter_state() -> FilterState:
    """Render sidebar filter widgets and return a FilterState.

    All filter values are persisted in st.session_state.
    Returns: FilterState dataclass.
    """
    st.sidebar.markdown("## 🎛️ Global Filters")

    # Platform multiselect
    platform_options = ["All"] + config.PLATFORMS
    platforms = st.sidebar.multiselect(
        "Platform",
        options=platform_options,
        default=st.session_state.get("sidebar_platforms", ["All"]),
        key="sidebar_platforms",
    )
    if not platforms:
        platforms = ["All"]

    # Time range selectbox
    time_range_label = st.sidebar.selectbox(
        "Time Range",
        options=list(_TIME_RANGE_OPTIONS.keys()),
        index=list(_TIME_RANGE_OPTIONS.keys()).index(
            st.session_state.get("sidebar_time_range", "Last 24h")
        ),
        key="sidebar_time_range",
    )

    custom_start = None
    custom_end   = None

    if time_range_label == "Custom":
        import datetime as _dt
        today = _dt.date.today()
        start_date = st.sidebar.date_input(
            "Start date", value=today - _dt.timedelta(days=1),
            key="sidebar_custom_start_date"
        )
        start_time = st.sidebar.time_input(
            "Start time", value=_dt.time(0, 0),
            key="sidebar_custom_start_time"
        )
        end_date = st.sidebar.date_input(
            "End date", value=today,
            key="sidebar_custom_end_date"
        )
        end_time = st.sidebar.time_input(
            "End time", value=_dt.time(23, 59),
            key="sidebar_custom_end_time"
        )
        custom_start = datetime.combine(start_date, start_time)
        custom_end   = datetime.combine(end_date,   end_time)
        st.session_state["sidebar_custom_start"] = custom_start
        st.session_state["sidebar_custom_end"]   = custom_end

    hours = _TIME_RANGE_OPTIONS.get(time_range_label, 24)

    return FilterState(
        platforms=platforms,
        time_range_label=time_range_label,
        time_range_hours=hours,
        custom_start=custom_start,
        custom_end=custom_end,
    )
