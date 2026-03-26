"""
kpi_comparator.py — Window comparison engine for the KPI Analyzer.

compare_windows(window_a, window_b, scope, platform) -> pd.DataFrame
"""
import pandas as pd
from typing import Tuple, Optional

import config
from storage.metrics_store import query_metrics


def _agg_window(
    start: str, end: str, platforms: list, metric_type: str = "all"
) -> pd.DataFrame:
    """Aggregate all metrics for a window into one value per (platform, code).

    Returns: DataFrame with columns platform, metric_type, code,
             stb_count, event_count, rate_per_1000.
    Parameters: start, end, platforms are SQL-parameterized in metrics_store.
    """
    rows = query_metrics(metric_type, platforms, ["all"], start, end)
    if not rows:
        return pd.DataFrame(columns=["platform", "metric_type", "code",
                                     "stb_count", "event_count", "rate_per_1000"])

    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["platform", "metric_type", "code"], as_index=False)
        .agg(
            stb_count=("stb_count", "sum"),
            event_count=("event_count", "sum"),
            rate_per_1000=("rate_per_1000", "mean"),
        )
    )
    return agg


def _classify(delta: float, pct_change: float, metric_type: str, code: str) -> str:
    """Return Degraded / Improved / Stable for a KPI change.

    Parameters are safe (internal computed values, not user-supplied).
    """
    if abs(pct_change) < 5:
        return "Stable"
    higher_is_worse = (
        metric_type in ["error_rate", "crash_rate", "cpu_utilization"]
        or code in ["MEM_HEAP_USED", "MEM_SWAP_USED", "THERMAL_THROTTLE"]
    )
    if higher_is_worse:
        return "Degraded" if delta > 0 else "Improved"
    # MEM_FREE_AVG: higher is better
    return "Improved" if delta > 0 else "Degraded"


def compare_windows(
    window_a: Tuple[str, str],
    window_b: Tuple[str, str],
    scope: str = "all",
    platform: str = "all",
) -> pd.DataFrame:
    """Compare KPI metrics between two time windows.

    Returns: DataFrame with columns platform, metric_type, code,
             value_a, value_b, delta, pct_change, status.
             Sorted by abs(pct_change) descending.
             pct_change is float; +inf serialized as '+inf%' in downstream callers.
    Parameters: all SQL-parameterized in metrics_store. No user input injected here.
    """
    import math

    platforms = config.PLATFORMS if platform == "all" else [platform]

    df_a = _agg_window(window_a[0], window_a[1], platforms, scope)
    df_b = _agg_window(window_b[0], window_b[1], platforms, scope)

    if df_a.empty and df_b.empty:
        return pd.DataFrame()

    merged = pd.merge(
        df_a, df_b,
        on=["platform", "metric_type", "code"],
        suffixes=("_a", "_b"),
        how="outer",
    ).fillna(0)

    merged.rename(columns={
        "rate_per_1000_a": "value_a",
        "rate_per_1000_b": "value_b",
    }, inplace=True)

    merged["delta"] = merged["value_b"] - merged["value_a"]

    def _pct(row):
        va, vb = row["value_a"], row["value_b"]
        if va == 0 and vb == 0:
            return 0.0
        if va == 0:
            return float("inf")
        return (row["delta"] / va) * 100

    merged["pct_change"] = merged.apply(_pct, axis=1)

    def _status(row):
        pct = row["pct_change"]
        if math.isinf(pct):
            pct_for_classify = 999.0
        else:
            pct_for_classify = pct
        return _classify(row["delta"], pct_for_classify,
                         row["metric_type"], row["code"])

    merged["status"] = merged.apply(_status, axis=1)

    # Sort by abs magnitude (inf first)
    merged["_sort_key"] = merged["pct_change"].apply(
        lambda x: float("inf") if math.isinf(x) else abs(x)
    )
    merged.sort_values("_sort_key", ascending=False, inplace=True)
    merged.drop(columns=["_sort_key", "stb_count_a", "stb_count_b",
                          "event_count_a", "event_count_b"],
                errors="ignore", inplace=True)

    return merged.reset_index(drop=True)
