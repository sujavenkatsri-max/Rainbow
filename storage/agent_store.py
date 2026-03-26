"""
agent_store.py — Agent conversation, memory, and trace read/write functions.

All SQL uses ? parameterized placeholders.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import config


def _get_conn() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with row_factory set."""
    conn = sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Short-term conversation memory ──────────────────────────────────────────

def load_short_term(session_id: str) -> List[Dict[str, Any]]:
    """Load the last AGENT_MEMORY_MAX_TURNS conversation turns for a session.

    Returns: list of {"role": str, "content": str|list} dicts ordered oldest-first.
    Parameter: session_id is SQL-parameterized.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT role, content FROM agent_conversation
                   WHERE session_id = ?
                   ORDER BY id ASC
                   LIMIT ?""",
                (session_id, config.AGENT_MEMORY_MAX_TURNS),
            ).fetchall()
            result = []
            for r in rows:
                try:
                    content = json.loads(r["content"])
                except (json.JSONDecodeError, TypeError):
                    content = r["content"]
                result.append({"role": r["role"], "content": content})
            return result
    except Exception as exc:
        print(f"[agent_store] load_short_term error: {exc}")
        return []


def save_short_term(session_id: str, history: List[Dict[str, Any]]) -> None:
    """Persist conversation history to the database, then trim to max turns.

    Returns: None.
    Parameters: session_id is SQL-parameterized; history content is JSON-serialized.
    """
    if not history:
        return
    try:
        now_str = datetime.now().isoformat()
        with _get_conn() as conn:
            rows = [
                (session_id, msg["role"],
                 json.dumps(msg["content"]) if not isinstance(msg["content"], str)
                 else msg["content"],
                 now_str)
                for msg in history
            ]
            conn.executemany(
                """INSERT INTO agent_conversation
                   (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)""",
                rows,
            )
            # Trim to max turns
            conn.execute(
                """DELETE FROM agent_conversation
                   WHERE session_id = ?
                     AND id NOT IN (
                       SELECT id FROM agent_conversation
                       WHERE session_id = ?
                       ORDER BY id DESC
                       LIMIT ?
                     )""",
                (session_id, session_id, config.AGENT_MEMORY_MAX_TURNS),
            )
            conn.commit()
    except Exception as exc:
        print(f"[agent_store] save_short_term error: {exc}")


def clear_short_term(session_id: str) -> None:
    """Delete all conversation turns for a session.

    Returns: None. Parameter: session_id is SQL-parameterized.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM agent_conversation WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
    except Exception as exc:
        print(f"[agent_store] clear_short_term error: {exc}")


# ── Long-term anomaly memory ─────────────────────────────────────────────────

def write_memory(
    metric_type: str,
    code: str,
    platform: str,
    observation: str,
    severity: str,
) -> None:
    """Write an anomaly observation to long-term memory with dedup.

    Skips write if (code, platform) already has an entry within
    AGENT_MEMORY_DEDUP_MINUTES of current time.

    Returns: None.
    Parameters: all fields are SQL-parameterized.
    """
    try:
        now = datetime.now()
        dedup_cutoff = (
            now - timedelta(minutes=config.AGENT_MEMORY_DEDUP_MINUTES)
        ).isoformat()

        with _get_conn() as conn:
            existing = conn.execute(
                """SELECT id FROM agent_memory
                   WHERE code = ? AND platform = ? AND timestamp >= ?""",
                (code, platform, dedup_cutoff),
            ).fetchone()
            if existing:
                return  # skip duplicate

            conn.execute(
                """INSERT INTO agent_memory
                   (timestamp, metric_type, code, platform, observation, severity)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now.isoformat(), metric_type, code, platform, observation, severity),
            )
            # Purge old entries
            conn.execute(
                """DELETE FROM agent_memory
                   WHERE timestamp < datetime('now', ? || ' days')""",
                (f"-{config.AGENT_MEMORY_RETENTION_DAYS}",),
            )
            conn.commit()
    except Exception as exc:
        print(f"[agent_store] write_memory error: {exc}")


def query_memory(
    code: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
) -> List[Dict[str, Any]]:
    """Query long-term anomaly memory, optionally filtered by code and/or platform.

    Returns: list of dicts with timestamp, metric_type, code, platform,
             observation, severity. Parameters are SQL-parameterized.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?"]
    params: List[Any] = [cutoff]

    if code:
        conditions.append("code = ?")
        params.append(code)
    if platform:
        conditions.append("platform = ?")
        params.append(platform)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT timestamp, metric_type, code, platform, observation, severity
        FROM agent_memory
        WHERE {where}
        ORDER BY timestamp DESC
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[agent_store] query_memory error: {exc}")
        return []


# ── Agent trace (observability) ──────────────────────────────────────────────

def log_trace(
    session_id: str,
    turn_id: int,
    step: int,
    tool_name: str,
    tool_input: Any,
    tool_output: Any,
    duration_ms: int,
    status: str,
) -> None:
    """Log a single tool-call step to the agent_trace table.

    tool_output is truncated to 2000 chars before storage.
    Returns: None. All parameters are SQL-parameterized.
    """
    try:
        input_str = json.dumps(tool_input) if not isinstance(tool_input, str) else tool_input
        output_str = json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output
        output_str = output_str[:2000]  # truncate

        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO agent_trace
                   (session_id, turn_id, step, tool_name, tool_input,
                    tool_output, duration_ms, status, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, turn_id, step, tool_name, input_str,
                 output_str, duration_ms, status, datetime.now().isoformat()),
            )
            conn.commit()
    except Exception as exc:
        print(f"[agent_store] log_trace error: {exc}")


def get_trace(session_id: str, turn_id: int) -> List[Dict[str, Any]]:
    """Retrieve all trace steps for a session+turn.

    Returns: list of dicts ordered by step ASC.
    Parameters: session_id and turn_id are SQL-parameterized.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT step, tool_name, tool_input, tool_output,
                          duration_ms, status, timestamp
                   FROM agent_trace
                   WHERE session_id = ? AND turn_id = ?
                   ORDER BY step ASC""",
                (session_id, turn_id),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[agent_store] get_trace error: {exc}")
        return []


def get_next_turn_id(session_id: str) -> int:
    """Return the next turn_id for a session (max existing + 1).

    Returns: int. Parameter: session_id is SQL-parameterized.
    """
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(turn_id) FROM agent_trace WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return (row[0] or 0) + 1
    except Exception as exc:
        print(f"[agent_store] get_next_turn_id error: {exc}")
        return 1


def get_agent_health_stats() -> Dict[str, Any]:
    """Aggregate health statistics across all agent sessions.

    Returns: dict with avg_steps_per_query, tool_call_frequency,
             guardrail_g1_hits, guardrail_g2_hits, empty_result_rate,
             avg_response_latency_ms.
    No user-supplied parameters.
    """
    try:
        with _get_conn() as conn:
            # Average steps per turn
            avg_row = conn.execute(
                """SELECT AVG(max_step) FROM (
                     SELECT session_id, turn_id, MAX(step)+1 as max_step
                     FROM agent_trace
                     GROUP BY session_id, turn_id
                   )"""
            ).fetchone()
            avg_steps = round(avg_row[0] or 0.0, 2)

            # Tool call frequency
            freq_rows = conn.execute(
                """SELECT tool_name, COUNT(*) as cnt
                   FROM agent_trace
                   WHERE tool_name IS NOT NULL
                   GROUP BY tool_name
                   ORDER BY cnt DESC"""
            ).fetchall()
            tool_freq = {r[0]: r[1] for r in freq_rows}

            # Empty result rate
            total = conn.execute("SELECT COUNT(*) FROM agent_trace").fetchone()[0] or 1
            empty = conn.execute(
                "SELECT COUNT(*) FROM agent_trace WHERE status = 'empty_result'"
            ).fetchone()[0]
            empty_rate = round((empty / total) * 100, 1)

            # Avg latency
            lat_row = conn.execute(
                "SELECT AVG(duration_ms) FROM agent_trace WHERE duration_ms IS NOT NULL"
            ).fetchone()
            avg_latency = round(lat_row[0] or 0.0, 1)

            # G1 hits (turns that hit max iterations — heuristic: turns with >= max_iter steps)
            g1 = conn.execute(
                f"""SELECT COUNT(*) FROM (
                      SELECT session_id, turn_id
                      FROM agent_trace
                      GROUP BY session_id, turn_id
                      HAVING MAX(step)+1 >= {config.AGENT_MAX_ITERATIONS}
                    )"""
            ).fetchone()[0]

            # G2 hits (tool calls returning time_range_exceeds error)
            g2 = conn.execute(
                """SELECT COUNT(*) FROM agent_trace
                   WHERE tool_output LIKE '%time_range_exceeds_48h_limit%'"""
            ).fetchone()[0]

            return {
                "avg_steps_per_query":    avg_steps,
                "tool_call_frequency":    tool_freq,
                "guardrail_g1_hits":      g1,
                "guardrail_g2_hits":      g2,
                "empty_result_rate":      empty_rate,
                "avg_response_latency_ms": avg_latency,
            }
    except Exception as exc:
        print(f"[agent_store] get_agent_health_stats error: {exc}")
        return {
            "avg_steps_per_query": 0.0,
            "tool_call_frequency": {},
            "guardrail_g1_hits": 0,
            "guardrail_g2_hits": 0,
            "empty_result_rate": 0.0,
            "avg_response_latency_ms": 0.0,
        }
