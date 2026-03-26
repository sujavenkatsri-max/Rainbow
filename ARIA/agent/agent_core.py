"""
agent_core.py — ReAct loop orchestrator for ARIA.

Public API: run_agent(user_message, session_id) -> tuple[str, list]
"""
import json
import time
from typing import Any, Dict, List, Tuple

import config
from agent import agent_memory, mock_llm
from agent.agent_tools import TOOL_REGISTRY
from agent.agent_observability import log_trace
from agent.tool_definitions import TOOL_DEFINITIONS
from storage.agent_store import get_next_turn_id


SYSTEM_PROMPT = """You are ARIA, an Automated Root-cause & Insights Analyst embedded in an STB
(Set-Top Box) KPI Monitoring dashboard for a media delivery operations team.

Your job is to help operations engineers understand STB device health by
analyzing error rates, crash rates, and CPU/memory utilization metrics
stored in a local SQLite time-series database.

The database is continuously populated by a background data engine running
alongside this application. Data is aggregated in 5-minute windows and
covers the last 24 hours. You must always query the database via your tools
to get current data — never assume or recall previous metric values.

PLATFORMS IN SCOPE: Apollo, EOS, Horizon, Liberty

METRIC TYPES:
- error_rate  → codes ERR_2001 through ERR_2008
- crash_rate  → codes CRR_3001 through CRR_3008
- cpu_utilization    → CPU_AVG, CPU_P95
- memory_utilization → MEM_FREE_AVG, MEM_HEAP_USED, MEM_SWAP_USED, THERMAL_THROTTLE

BEHAVIORAL RULES:
1. Always use tools to retrieve data before making any claims about metric values.
2. Never state a metric value you did not receive from a tool result in this conversation turn.
3. When time references are ambiguous, always call resolve_time_reference first.
4. Keep prose responses under 300 words. For tables and delta reports, render structured output.
5. Cite the metric code, platform, and time window for every numerical claim.
6. If a tool returns empty data, state: "No data available for [metric] on [platform]."
7. When identifying degradation, state the metric code, magnitude, time window, and one plausible cause.
8. If a query requires more than 6 tool calls, respond with partial findings.
9. When asked "has this happened before", query long-term agent memory before responding.
10. You are read-only. You have no ability to modify data or access external systems.

RESPONSE FORMAT:
- Lead with the direct answer.
- Follow with supporting metric values (cited with code + platform + time).
- End with a recommended next step if applicable.
- Use bullet points only for lists of 3+ items.
- Bold only metric codes and severity labels."""


def _dispatch_tool(
    tool_name: str,
    tool_input: Dict,
    session_id: str,
    turn_id: int,
    step: int,
) -> Dict:
    """Call the named tool with injected observability args.

    Returns standard envelope dict.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"status": "error", "data": None,
                "meta": {"tool_name": tool_name, "reason": "tool_not_found"}}

    # Inject observability params
    kwargs = dict(tool_input)
    kwargs["_session_id"] = session_id
    kwargs["_turn_id"]    = turn_id
    kwargs["_step"]       = step

    return fn(**kwargs)


def run_agent(user_message: str, session_id: str) -> Tuple[str, List[Dict]]:
    """Run the ARIA ReAct loop for a single user message.

    Returns: (response_text, trace_steps)
    """
    # Load short-term memory
    history = agent_memory.load_short_term(session_id)

    # Inject long-term memory as context prefix when relevant
    import re
    if re.search(r"before|happened before|recurring|again", user_message, re.IGNORECASE):
        memories = agent_memory.query_memory()
        if memories:
            mem_lines = "\n".join(
                f"  [{m['timestamp'][:16]}] {m['code']} on {m['platform']}: "
                f"{m['observation']} ({m['severity']})"
                for m in memories[:10]
            )
            user_message = (
                f"[Long-term memory context — past anomaly observations:]\n"
                f"{mem_lines}\n\n"
                f"[User question:] {user_message}"
            )

    history.append({"role": "user", "content": user_message})

    trace: List[Dict] = []
    iteration = 0
    turn_id = get_next_turn_id(session_id)
    gathered_results: List[Dict] = []

    while iteration < config.AGENT_MAX_ITERATIONS:
        try:
            response = mock_llm.create(
                model=config.AGENT_MODEL,
                max_tokens=config.AGENT_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=history,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as exc:
            final_text = f"ARIA encountered an internal error: {exc}"
            return final_text, trace

        if response.stop_reason == "tool_use":
            # Process all tool_use blocks in this response
            tool_use_blocks = [
                b for b in response.content
                if (hasattr(b, "type") and getattr(b, "type", None) == "tool_use")
                or (isinstance(b, dict) and b.get("type") == "tool_use")
            ]

            if not tool_use_blocks:
                # No tool blocks despite tool_use — treat as end_turn
                break

            # Serialize content blocks to dicts before storing in history
            def _serialize_block(b):
                if isinstance(b, dict):
                    return b
                if hasattr(b, "__dataclass_fields__"):
                    return {f: getattr(b, f) for f in b.__dataclass_fields__}
                return {"type": "text", "text": str(b)}

            serialized_content = [_serialize_block(b) for b in response.content]
            history.append({"role": "assistant", "content": serialized_content})

            for block in tool_use_blocks:
                if hasattr(block, "name"):
                    tool_name  = block.name
                    tool_id    = block.id
                    tool_input = block.input
                else:
                    tool_name  = block.get("name", "")
                    tool_id    = block.get("id", "")
                    tool_input = block.get("input", {})

                t_start = time.time()
                try:
                    result = _dispatch_tool(tool_name, tool_input,
                                            session_id, turn_id, iteration)
                    status = ("empty_result" if result.get("status") == "empty"
                              else "error" if result.get("status") == "error"
                              else "success")
                except Exception as exc:
                    result = {"status": "error", "data": None,
                              "meta": {"tool_name": tool_name, "reason": str(exc)}}
                    status = "error"

                duration_ms = int((time.time() - t_start) * 1000)

                trace.append({
                    "step":        iteration,
                    "tool_name":   tool_name,
                    "tool_input":  tool_input,
                    "tool_output": result,
                    "duration_ms": duration_ms,
                    "status":      status,
                })
                gathered_results.append(result)

                # Append tool result to history
                history.append({
                    "role": "user",
                    "content": [
                        {
                            "type":        "tool_result",
                            "tool_use_id": tool_id,
                            "content":     json.dumps(result),
                        }
                    ],
                })

            iteration += 1

        elif response.stop_reason == "end_turn":
            # Extract final text (blocks may be dataclasses or dicts)
            final_text = ""
            for block in response.content:
                btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
                if btype == "text":
                    final_text += getattr(block, "text", "") or (block.get("text", "") if isinstance(block, dict) else "")
            if not final_text:
                final_text = "Analysis complete."

            history.append({"role": "assistant", "content": final_text})
            # Persist conversation history (trim happens inside save_short_term)
            agent_memory.save_short_term(session_id, history)
            return final_text, trace

        else:
            # Unknown stop reason
            break

    # Guardrail G1: max iterations reached
    summary_parts = []
    for r in gathered_results:
        if r.get("status") == "ok" and r.get("data"):
            meta = r.get("meta", {})
            summary_parts.append(
                f"[{meta.get('tool_name','tool')}] returned "
                f"{meta.get('row_count', '?')} rows for {meta.get('time_range','?')}"
            )

    partial = (
        "Analysis incomplete — maximum reasoning steps reached. "
        "Based on what I found so far: "
        + ("; ".join(summary_parts) if summary_parts else "no data retrieved.")
    )
    history.append({"role": "assistant", "content": partial})
    agent_memory.save_short_term(session_id, history)
    return partial, trace
