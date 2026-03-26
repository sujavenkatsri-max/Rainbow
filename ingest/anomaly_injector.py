"""
anomaly_injector.py — Demo anomaly injection for ARIA STB KPI Analyzer.

Resolves T-Nh time references relative to seed_start_time and applies
event_count multipliers to matching records.

If config.ANOMALY_INJECTION_ENABLED is False, all public functions are no-ops.
"""
import re
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any

import config
from ingest.schema import MetricRecord


def _resolve_time_ref(ref: str, seed_start: datetime) -> datetime:
    """Resolve a 'T-Nh' string to an absolute datetime.

    T is treated as the end of the seed window (seed_start + 24h ≈ now).
    So T-4h = seed_start + 24h - 4h = ~4 hours before current time.

    Parameters:
        ref: str — e.g. 'T-4h', 'T-2.5h'. Internal use only, not user-supplied.
        seed_start: datetime anchor (start of 24h seed window).

    Returns: datetime.
    """
    match = re.match(r"T-(\d+(?:\.\d+)?)h", ref)
    if not match:
        raise ValueError(f"Unrecognized time reference: {ref!r}")
    hours = float(match.group(1))
    seed_end = seed_start + timedelta(hours=24)
    return seed_end - timedelta(hours=hours)


def build_multiplier_map(
    seed_start: datetime,
    current_timestamp: datetime,
) -> Dict[tuple, float]:
    """Return a {(platform, code): multiplier} dict for the given timestamp.

    Returns: dict, possibly empty if no anomaly window covers the timestamp.
    Parameters are internal — not user-supplied.
    """
    if not config.ANOMALY_INJECTION_ENABLED:
        return {}

    result: Dict[tuple, float] = {}
    for event in config.ANOMALY_EVENTS:
        start = _resolve_time_ref(event["start_time"], seed_start)
        end   = _resolve_time_ref(event["end_time"],   seed_start)
        if start <= current_timestamp <= end:
            for code in event["codes"]:
                result[(event["platform"], code)] = event["multiplier"]
    return result


def apply_demo_anomalies(seed_start: datetime) -> None:
    """UPDATE existing seeded rows in the metrics table for all anomaly windows.

    This is called once after seeding to stamp the pre-wired demo events
    into the historical data.

    Returns: None.
    Parameters: seed_start is internal — not user-supplied.
    All SQL is parameterized.
    """
    if not config.ANOMALY_INJECTION_ENABLED:
        return

    try:
        with sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False) as conn:
            for event in config.ANOMALY_EVENTS:
                start = _resolve_time_ref(event["start_time"], seed_start)
                end   = _resolve_time_ref(event["end_time"],   seed_start)
                start_str = start.isoformat()
                end_str   = end.isoformat()
                multiplier = event["multiplier"]
                platform   = event["platform"]

                for code in event["codes"]:
                    # Read matching rows
                    rows = conn.execute(
                        """SELECT id, stb_count, event_count
                           FROM metrics
                           WHERE platform = ?
                             AND code     = ?
                             AND timestamp >= ?
                             AND timestamp <= ?""",
                        (platform, code, start_str, end_str),
                    ).fetchall()

                    for row_id, stb_count, event_count in rows:
                        new_event_count = max(0, int(event_count * multiplier))
                        stb_count_safe  = max(1, stb_count)
                        new_rate        = (new_event_count / stb_count_safe) * 1000
                        conn.execute(
                            """UPDATE metrics
                               SET event_count = ?, rate_per_1000 = ?
                               WHERE id = ?""",
                            (new_event_count, new_rate, row_id),
                        )
                conn.commit()
    except Exception as exc:
        print(f"[anomaly_injector] apply_demo_anomalies error: {exc}")
