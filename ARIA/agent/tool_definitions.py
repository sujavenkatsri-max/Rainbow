"""
tool_definitions.py — JSON tool schemas in exact Anthropic tool format.

TOOL_DEFINITIONS is imported by both mock_llm.py and agent_core.py.
Never duplicate schemas — always import this list.
"""

TOOL_DEFINITIONS = [
    {
        "name": "query_metrics",
        "description": (
            "Query the STB metrics database for timeseries data. "
            "Returns aggregated records grouped by timestamp, platform, and code. "
            "Rejects time ranges > 48 hours."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_type": {
                    "type": "string",
                    "enum": ["error_rate", "crash_rate", "cpu_utilization",
                             "memory_utilization", "all"],
                    "description": "Metric category to query.",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform name or 'all' for all platforms.",
                },
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of metric codes, or ['all'] for all codes.",
                },
                "start_time": {
                    "type": "string",
                    "description": "ISO 8601 start timestamp.",
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO 8601 end timestamp.",
                },
            },
            "required": ["metric_type", "platform", "codes", "start_time", "end_time"],
        },
    },
    {
        "name": "compare_kpi_windows",
        "description": (
            "Compare KPI metrics between two time windows (Window A and Window B). "
            "Returns delta, pct_change, and Degraded/Improved/Stable status for each KPI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_a_start": {"type": "string", "description": "Window A start (ISO 8601)."},
                "window_a_end":   {"type": "string", "description": "Window A end (ISO 8601)."},
                "window_b_start": {"type": "string", "description": "Window B start (ISO 8601)."},
                "window_b_end":   {"type": "string", "description": "Window B end (ISO 8601)."},
                "platform": {
                    "type": "string",
                    "description": "Platform name or 'all'.",
                },
                "metric_type": {
                    "type": "string",
                    "enum": ["error_rate", "crash_rate", "cpu_utilization",
                             "memory_utilization", "all"],
                    "description": "Metric type to compare, or 'all'.",
                },
            },
            "required": ["window_a_start", "window_a_end",
                         "window_b_start", "window_b_end", "platform"],
        },
    },
    {
        "name": "detect_anomalies",
        "description": (
            "Detect statistical anomalies (z-score) in a time window compared to "
            "a 24-hour rolling baseline. Writes findings to long-term agent memory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "string", "description": "Inspection window start (ISO 8601)."},
                "end_time":   {"type": "string", "description": "Inspection window end (ISO 8601)."},
                "platform": {
                    "type": "string",
                    "description": "Platform name or 'all'.",
                },
                "threshold": {
                    "type": "number",
                    "description": "Z-score threshold (default 2.0).",
                },
            },
            "required": ["start_time", "end_time", "platform"],
        },
    },
    {
        "name": "get_top_movers",
        "description": (
            "Get the KPIs with the largest percentage change between two windows. "
            "Delegates to compare_kpi_windows internally."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_a_start": {"type": "string"},
                "window_a_end":   {"type": "string"},
                "window_b_start": {"type": "string"},
                "window_b_end":   {"type": "string"},
                "platform":       {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["degraded", "improved", "both"],
                    "description": "Filter by change direction.",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of results to return (1–20, default 5).",
                },
            },
            "required": ["window_a_start", "window_a_end",
                         "window_b_start", "window_b_end", "platform"],
        },
    },
    {
        "name": "get_current_snapshot",
        "description": (
            "Return the most recent 5-minute window values for requested KPIs and platform."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform name or 'all'.",
                },
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of codes, or ['all'] for all.",
                },
            },
            "required": ["platform"],
        },
    },
    {
        "name": "resolve_time_reference",
        "description": (
            "Convert a natural language time reference (e.g. '3 PM', 'this morning', "
            "'2 hours ago') into absolute ISO 8601 start/end timestamps snapped to 5-min boundaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "time_reference": {
                    "type": "string",
                    "description": "Natural language time expression.",
                },
                "anchor": {
                    "type": "string",
                    "description": "Optional ISO 8601 anchor datetime (defaults to now).",
                },
            },
            "required": ["time_reference"],
        },
    },
    {
        "name": "summarize_panel",
        "description": (
            "Generate a structured summary for a panel including trend direction, "
            "top codes, active alerts, and a plain-language narrative."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "panel": {
                    "type": "string",
                    "enum": ["error_rate", "crash_rate", "resource"],
                    "description": "Which panel to summarize.",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform name or 'all'.",
                },
                "time_range_hours": {
                    "type": "integer",
                    "description": "Hours of history to summarize (default 6).",
                },
            },
            "required": ["panel", "platform"],
        },
    },
]
