"""
metrics_store.py — Metric read/write functions for the ARIA SQLite store.

All SQL uses ? parameterized placeholders. No f-strings or .format() for SQL values.
All bulk inserts use executemany(). The background engine is the sole writer.
"""
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any

import config
from ingest.schema import MetricRecord


def _get_conn() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with row_factory set."""
    conn = sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def insert_metric_batch(records: List[MetricRecord]) -> None:
    """Bulk-insert a list of MetricRecord objects into the metrics table.

    Returns: None
    Parameters: records is safe (internal dataclass), no user input.
    Uses INSERT OR REPLACE to handle duplicate timestamp+platform+code gracefully.
    """
    if not records:
        return
    rows = [
        (r.timestamp, r.platform, r.metric_type, r.code,
         r.stb_count, r.event_count, r.rate_per_1000)
        for r in records
    ]
    try:
        with _get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO metrics
                   (timestamp, platform, metric_type, code,
                    stb_count, event_count, rate_per_1000)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
    except Exception as exc:
        print(f"[metrics_store] insert_metric_batch error: {exc}")


def query_metrics(
    metric_type: str,
    platforms: List[str],
    codes: List[str],
    start_time: str,
    end_time: str,
) -> List[Dict[str, Any]]:
    """Query and aggregate metrics from the database.

    Returns: list of dicts with keys timestamp, platform, metric_type, code,
             stb_count, event_count, rate_per_1000.
    Parameters: metric_type, platforms, codes, start_time, end_time are all
                SQL-parameterized — never interpolated into the query string.
    """
    # Expand "all" codes
    if codes == ["all"] or codes == "all":
        if metric_type in config.CODES_BY_METRIC_TYPE:
            codes = config.CODES_BY_METRIC_TYPE[metric_type]
        else:
            # Aggregate across all metric types
            all_codes = []
            for c_list in config.CODES_BY_METRIC_TYPE.values():
                all_codes.extend(c_list)
            codes = all_codes

    # Expand "all" platforms
    if platforms == ["all"] or platforms == "all":
        platforms = config.PLATFORMS

    if not codes or not platforms:
        return []

    p_placeholders = ",".join("?" * len(platforms))
    c_placeholders = ",".join("?" * len(codes))

    if metric_type == "all":
        type_clause = ""
        type_params = []
    else:
        type_clause = "AND metric_type = ?"
        type_params = [metric_type]

    sql = f"""
        SELECT timestamp, platform, metric_type, code,
               SUM(stb_count)     AS stb_count,
               SUM(event_count)   AS event_count,
               AVG(rate_per_1000) AS rate_per_1000
        FROM metrics
        WHERE platform   IN ({p_placeholders})
          AND code       IN ({c_placeholders})
          AND timestamp  >= ?
          AND timestamp  <= ?
          {type_clause}
        GROUP BY timestamp, platform, metric_type, code
        ORDER BY timestamp ASC
    """
    params = [*platforms, *codes, start_time, end_time, *type_params]

    try:
        with _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[metrics_store] query_metrics error: {exc}")
        return []


def get_available_time_range() -> Tuple[str, str]:
    """Return (min_timestamp, max_timestamp) from the metrics table.

    Returns: tuple of two ISO 8601 strings, or (now-24h, now) on error.
    No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM metrics"
            ).fetchone()
            if row and row[0] and row[1]:
                return row[0], row[1]
    except Exception as exc:
        print(f"[metrics_store] get_available_time_range error: {exc}")
    now = datetime.now()
    return (now - timedelta(hours=24)).isoformat(), now.isoformat()


def get_latest_timestamp() -> str:
    """Return the most recent timestamp string in the metrics table.

    Returns: ISO 8601 string, or current time isoformat on error.
    No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) FROM metrics"
            ).fetchone()
            if row and row[0]:
                return row[0]
    except Exception as exc:
        print(f"[metrics_store] get_latest_timestamp error: {exc}")
    return datetime.now().isoformat()


def purge_old_metrics(hours: int) -> int:
    """Delete records older than `hours` hours.

    Returns: number of rows deleted.
    Parameter: hours is safe (integer, internal use only).
    """
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM metrics WHERE timestamp < datetime('now', ? || ' hours')",
                (f"-{hours}",),
            )
            conn.commit()
            return cursor.rowcount
    except Exception as exc:
        print(f"[metrics_store] purge_old_metrics error: {exc}")
        return 0


def is_seeded() -> bool:
    """Return True if the seed_status table has a seeded=1 row.

    Returns: bool. No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT seeded FROM seed_status WHERE id = 1"
            ).fetchone()
            return bool(row and row[0] == 1)
    except Exception as exc:
        print(f"[metrics_store] is_seeded error: {exc}")
        return False


def mark_seeded() -> None:
    """Write seeded=1 into seed_status table with current timestamp.

    Returns: None. No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO seed_status (id, seeded, seeded_at)
                   VALUES (1, 1, ?)""",
                (datetime.now().isoformat(),),
            )
            conn.commit()
    except Exception as exc:
        print(f"[metrics_store] mark_seeded error: {exc}")


def reset_seed_flag() -> None:
    """Clear the seeded flag (used by reset_db demo flow).

    Returns: None. No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO seed_status (id, seeded) VALUES (1, 0)"
            )
            conn.commit()
    except Exception as exc:
        print(f"[metrics_store] reset_seed_flag error: {exc}")
