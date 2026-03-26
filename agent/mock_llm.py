# HACKATHON MODE: Replace with real Anthropic SDK when USE_MOCK_LLM=False
"""
mock_llm.py — Internal Claude API simulation for ARIA.

Exposes create() with identical signature to anthropic.client.messages.create().
Routes to real Anthropic SDK when config.USE_MOCK_LLM = False.

synthesize_response() builds grounded answers from actual tool results in
conversation history — never fabricates numbers.
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config


# ── Message dataclasses (mirror anthropic.types) ────────────────────────────

@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class MockMessage:
    content: list
    role: str = "assistant"
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use"


# ── Intent routing ───────────────────────────────────────────────────────────

# Checked in priority order; first match wins.
INTENT_RULES = [
    (r"compar|differ|between|change|before.*after|vs\b",
     "compare_kpi_windows", "resolve_time_reference"),
    (r"anomal|spike|unusual|alert|abnormal",
     "detect_anomalies", None),
    (r"\btop\b|most|worst|highest|biggest",
     "get_top_movers", None),
    (r"current|right now|latest|now\b",
     "get_current_snapshot", None),
    (r"summar|overview|how is|status of",
     "summarize_panel", None),
    (r"before|happened before|recurring|again",
     "get_current_snapshot", "memory_query"),
    (r"\d{1,2}\s*(am|pm|:)|hours? ago|minutes? ago|morning|afternoon|evening|night|yesterday|today",
     "resolve_time_reference", None),
]
FALLBACK_TOOL = "get_current_snapshot"


def _classify_intent(text: str):
    """Return (primary_tool, secondary_tool) for the user message."""
    text_lower = text.lower()
    for pattern, primary, secondary in INTENT_RULES:
        if re.search(pattern, text_lower):
            return primary, secondary
    return FALLBACK_TOOL, None


def _extract_platform(text: str) -> str:
    """Extract platform name from message text, default 'all'."""
    text_lower = text.lower()
    for p in config.PLATFORMS:
        if p.lower() in text_lower:
            return p
    return "all"


def _extract_time_range_from_text(text: str) -> Optional[tuple]:
    """Try to extract a time range hint from message text.

    Returns: (start_iso, end_iso) or None.
    """
    m = re.search(r"last\s+(\d+)\s*h", text.lower())
    if m:
        hours = int(m.group(1))
        end = datetime.now()
        start = end - timedelta(hours=hours)
        return start.isoformat(), end.isoformat()
    return None


def _extract_time_refs_from_text(text: str) -> List[str]:
    """Extract natural language time references from message text."""
    patterns = [
        r"\d{1,2}\s*(?:am|pm)",
        r"\d{1,2}:\d{2}",
        r"\d+\s*hours?\s*ago",
        r"\d+\s*minutes?\s*ago",
        r"this\s+(?:morning|afternoon|evening)",
        r"last\s+night",
        r"yesterday",
        r"today",
    ]
    refs = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            refs.append(m.group(0))
    return refs


def _build_tool_calls(primary: str, secondary: str, messages: List[Dict]) -> List[ToolUseBlock]:
    """Build ToolUseBlock list based on intent + conversation context."""
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_user = content
                break
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        last_user = block.get("text", "")
                        break
                if last_user:
                    break

    platform = _extract_platform(last_user)
    calls = []

    # If there are unresolved time references, resolve them first
    time_refs = _extract_time_refs_from_text(last_user)
    if time_refs and primary != "resolve_time_reference":
        for ref in time_refs[:1]:  # resolve the first one
            calls.append(ToolUseBlock(
                type="tool_use",
                id=f"toolu_{uuid.uuid4().hex[:8]}",
                name="resolve_time_reference",
                input={"time_reference": ref},
            ))
        # Return just the resolve call; next iteration will proceed with comparison
        if calls:
            return calls

    now = datetime.now()
    end_default = now.isoformat()
    start_default = (now - timedelta(hours=6)).isoformat()
    time_range = _extract_time_range_from_text(last_user)
    if time_range:
        start_default, end_default = time_range

    if primary == "get_current_snapshot":
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="get_current_snapshot",
            input={"platform": platform, "codes": ["all"]},
        ))
    elif primary == "detect_anomalies":
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="detect_anomalies",
            input={
                "start_time": start_default,
                "end_time":   end_default,
                "platform":   platform,
                "threshold":  config.ANOMALY_ZSCORE_WARNING,
            },
        ))
    elif primary == "get_top_movers":
        mid = (now - timedelta(hours=3)).isoformat()
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="get_top_movers",
            input={
                "window_a_start": start_default,
                "window_a_end":   mid,
                "window_b_start": mid,
                "window_b_end":   end_default,
                "platform":       platform,
                "direction":      "degraded",
                "top_n":          5,
            },
        ))
    elif primary == "compare_kpi_windows":
        mid = (now - timedelta(hours=3)).isoformat()
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="compare_kpi_windows",
            input={
                "window_a_start": start_default,
                "window_a_end":   mid,
                "window_b_start": mid,
                "window_b_end":   end_default,
                "platform":       platform,
                "metric_type":    "all",
            },
        ))
    elif primary == "summarize_panel":
        panel = "error_rate"
        if re.search(r"crash", last_user, re.IGNORECASE):
            panel = "crash_rate"
        elif re.search(r"cpu|memory|resource", last_user, re.IGNORECASE):
            panel = "resource"
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="summarize_panel",
            input={"panel": panel, "platform": platform, "time_range_hours": 6},
        ))
    elif primary == "resolve_time_reference":
        ref = time_refs[0] if time_refs else last_user
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="resolve_time_reference",
            input={"time_reference": ref},
        ))
    else:
        calls.append(ToolUseBlock(
            type="tool_use",
            id=f"toolu_{uuid.uuid4().hex[:8]}",
            name="get_current_snapshot",
            input={"platform": platform, "codes": ["all"]},
        ))

    return calls


# ── Tool result synthesis ────────────────────────────────────────────────────

def _extract_tool_results(messages: List[Dict]) -> List[Dict]:
    """Pull all tool_result content blocks from the most recent agent turn."""
    results = []
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        try:
                            data = json.loads(block.get("content", "{}"))
                        except (json.JSONDecodeError, TypeError):
                            data = {}
                        results.append(data)
    return results


def _get_last_user_text(messages: List[Dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return ""


def synthesize_response(messages: List[Dict]) -> MockMessage:
    """Build a grounded natural-language response from tool results in history.

    Never fabricates numbers — all values come from tool results.
    Returns MockMessage with stop_reason='end_turn'.
    """
    tool_results = _extract_tool_results(messages)
    user_question = _get_last_user_text(messages)

    if not tool_results:
        text = (
            "I queried the STB metrics database but did not receive any data. "
            "The database may still be seeding. Please try again in a moment."
        )
        return MockMessage(content=[TextBlock(text=text)], stop_reason="end_turn")

    parts = []
    for result in tool_results:
        status = result.get("status", "error")
        data   = result.get("data")
        meta   = result.get("meta", {})
        tool   = meta.get("tool_name", "unknown")

        if status == "error":
            reason = result.get("meta", {}).get("reason") or result.get("reason", "unknown error")
            parts.append(f"Tool `{tool}` returned an error: {reason}.")
            continue

        if status == "empty" or not data:
            tr = meta.get("time_range", "requested period")
            parts.append(f"No data available from `{tool}` for {tr}.")
            continue

        # Snapshot
        if tool == "get_current_snapshot" and isinstance(data, list):
            rows = data[:10]
            lines = []
            for r in rows:
                lines.append(
                    f"  [{r['code']} | {r['platform']}] "
                    f"rate={r['rate_per_1000']:.2f}/1k, "
                    f"events={r['event_count']}, stbs={r['stb_count']}"
                )
            parts.append(
                f"**Current snapshot** (as of {meta.get('time_range','latest')}):\n"
                + "\n".join(lines)
            )

        # Comparison
        elif tool == "compare_kpi_windows" and isinstance(data, list):
            top = data[:5]
            lines = []
            for r in top:
                lines.append(
                    f"  **{r['code']}** [{r['platform']}]: "
                    f"{r['value_a']:.2f} → {r['value_b']:.2f} "
                    f"({r['pct_change']}) — {r['status']}"
                )
            time_range = meta.get("time_range", "")
            parts.append(
                f"**KPI comparison** ({time_range}):\n"
                + "\n".join(lines)
            )

        # Anomalies
        elif tool == "detect_anomalies" and isinstance(data, list):
            lines = []
            for a in data[:8]:
                lines.append(
                    f"  **{a['code']}** [{a['platform']}] "
                    f"z={a['z_score']:.1f}, "
                    f"observed={a['observed']:.2f}, "
                    f"baseline={a['baseline_mean']:.2f} "
                    f"— **{a['severity']}**"
                )
            parts.append(
                f"**Anomalies detected** ({meta.get('time_range','')}):\n"
                + ("\n".join(lines) if lines else "  None above threshold.")
            )

        # Top movers
        elif tool == "get_top_movers" and isinstance(data, list):
            lines = []
            for r in data:
                lines.append(
                    f"  **{r['code']}** [{r['platform']}]: "
                    f"{r['pct_change']} — {r['status']}"
                )
            parts.append("**Top movers**:\n" + "\n".join(lines))

        # Summary
        elif tool == "summarize_panel" and isinstance(data, dict):
            parts.append(data.get("narrative", "Summary unavailable."))

        # Time resolution
        elif tool == "resolve_time_reference" and isinstance(data, dict):
            parts.append(
                f"Time reference resolved: **{data.get('label','')}** "
                f"→ {data.get('start','')} to {data.get('end','')}."
            )

        else:
            parts.append(f"Tool `{tool}` returned {meta.get('row_count', 0)} rows.")

    response_text = "\n\n".join(parts) if parts else "No findings to report."

    # Add recommended next step
    if any("Degraded" in p for p in parts):
        response_text += (
            "\n\n**Recommended next step**: Run `compare_kpi_windows` over a wider "
            "time range or check the KPI Analyzer for detailed delta breakdown."
        )
    elif any("Anomalies detected" in p for p in parts):
        response_text += (
            "\n\n**Recommended next step**: Correlate with the crash rate panel "
            "and check if the anomaly aligns with a deployment or config change."
        )

    return MockMessage(content=[TextBlock(text=response_text)], stop_reason="end_turn")


# ── Public API (mirrors anthropic.client.messages.create) ───────────────────

def _check_pending_tool_results(messages: List[Dict]) -> bool:
    """Return True if the last assistant message was tool_use and result is in history."""
    # Find last assistant message
    last_assistant_stop = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        last_assistant_stop = "tool_use"
                        break
                    if hasattr(block, "type") and block.type == "tool_use":
                        last_assistant_stop = "tool_use"
                        break
            break

    if last_assistant_stop != "tool_use":
        return False

    # Check if there's a subsequent user message with tool_result
    found_assistant = False
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and not found_assistant:
            found_assistant = True
            continue
        if found_assistant and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        return True
            break
    return False


def _mock_create(model, max_tokens, system, messages, tools) -> MockMessage:
    """Internal mock implementation of messages.create()."""
    try:
        # If tool results just came back, synthesize final answer
        if _check_pending_tool_results(messages):
            return synthesize_response(messages)

        # Classify intent and build tool calls
        user_text = _get_last_user_text(messages)
        primary, secondary = _classify_intent(user_text)
        tool_calls = _build_tool_calls(primary, secondary, messages)

        if tool_calls:
            return MockMessage(content=tool_calls, stop_reason="tool_use")

        # Fallback
        return synthesize_response(messages)

    except Exception:
        return MockMessage(
            content=[TextBlock(
                text="I encountered an unexpected issue. Please try rephrasing your question."
            )],
            stop_reason="end_turn",
        )


def create(model, max_tokens, system, messages, tools) -> MockMessage:
    """Public entry point — mirrors anthropic.client.messages.create().

    Routes to real Anthropic SDK when USE_MOCK_LLM=False.
    """
    if not config.USE_MOCK_LLM:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
    return _mock_create(model, max_tokens, system, messages, tools)
