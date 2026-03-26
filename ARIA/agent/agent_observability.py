"""
agent_observability.py — Trace logging and health stats for ARIA agent.

Delegates to storage.agent_store for all database operations.
"""
from typing import List, Dict, Any

from storage import agent_store


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

    Returns: None. All parameters SQL-parameterized in agent_store.
    """
    agent_store.log_trace(
        session_id, turn_id, step, tool_name,
        tool_input, tool_output, duration_ms, status,
    )


def get_trace(session_id: str, turn_id: int) -> List[Dict[str, Any]]:
    """Retrieve all trace steps for a session+turn.

    Returns: list of trace dicts ordered by step ASC.
    """
    return agent_store.get_trace(session_id, turn_id)


def get_agent_health_stats() -> Dict[str, Any]:
    """Aggregate health statistics across all agent sessions.

    Returns: dict with avg_steps_per_query, tool_call_frequency, etc.
    """
    return agent_store.get_agent_health_stats()
