"""
agent_memory.py — Short-term and long-term memory functions for ARIA agent.

Delegates to storage.agent_store for all database operations.
"""
from typing import List, Dict, Any, Optional

from storage import agent_store


def load_short_term(session_id: str) -> List[Dict[str, Any]]:
    """Load the last AGENT_MEMORY_MAX_TURNS turns for a session.

    Returns: list of {"role": str, "content": ...} dicts ordered oldest-first.
    Parameter session_id is SQL-parameterized in agent_store.
    """
    return agent_store.load_short_term(session_id)


def save_short_term(session_id: str, history: List[Dict[str, Any]]) -> None:
    """Persist new conversation turns and trim to max turns.

    Returns: None. Parameter session_id is SQL-parameterized in agent_store.
    """
    agent_store.save_short_term(session_id, history)


def write_memory(
    metric_type: str,
    code: str,
    platform: str,
    observation: str,
    severity: str,
) -> None:
    """Write an anomaly observation to long-term memory with dedup.

    Returns: None. All parameters are SQL-parameterized in agent_store.
    """
    agent_store.write_memory(metric_type, code, platform, observation, severity)


def query_memory(
    code: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
) -> List[Dict[str, Any]]:
    """Query long-term anomaly memory.

    Returns: list of memory entry dicts. Parameters SQL-parameterized in agent_store.
    """
    return agent_store.query_memory(code=code, platform=platform, days=days)


def get_next_turn_id(session_id: str) -> int:
    """Return next turn_id for a session.

    Returns: int. Parameter SQL-parameterized in agent_store.
    """
    return agent_store.get_next_turn_id(session_id)
