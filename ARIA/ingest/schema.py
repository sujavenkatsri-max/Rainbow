"""
schema.py — MetricRecord dataclass for the ARIA STB KPI Analyzer.
"""
from dataclasses import dataclass


@dataclass
class MetricRecord:
    """A single 5-minute aggregated metric record for one platform + code."""

    timestamp: str      # ISO 8601, snapped to 5-min boundary e.g. "2025-03-26T14:05:00"
    platform: str       # "Apollo" | "EOS" | "Horizon" | "Liberty"
    metric_type: str    # "error_rate" | "crash_rate" | "cpu_utilization" | "memory_utilization"
    code: str           # e.g. "ERR_2003", "CRR_3002", "CPU_AVG"
    stb_count: int      # unique STBs reporting this metric in the window (>= 1)
    event_count: int    # total events across all reporting STBs (>= 0)
    rate_per_1000: float  # (event_count / stb_count) * 1000
