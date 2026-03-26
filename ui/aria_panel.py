"""
aria_panel.py — ARIA chat UI component.

render_aria_panel() -> None
"""
import uuid
import streamlit as st

from agent import agent_core
from storage import agent_store


_SUGGESTION_CHIPS = [
    "What are the current error rates on Apollo?",
    "Compare all KPIs between the last 6h and previous 6h",
    "Which crash code spiked most in the last 3 hours?",
    "Were there any anomalies in the last 6 hours?",
    "What were the top 3 most degraded KPIs today?",
    "Has ERR_2003 spiked like this before?",
]


def _handle_user_input(prompt: str) -> None:
    """Process user input: call ARIA, append to history, rerun.

    Parameters:
        prompt: str — user message. Passed to agent_core.run_agent(),
                not SQL-injected anywhere in this function.
    """
    session_id = st.session_state["session_id"]

    # Append user message first
    st.session_state["aria_history"].append({"role": "user", "content": prompt})

    with st.spinner("ARIA is thinking..."):
        try:
            response_text, trace = agent_core.run_agent(prompt, session_id)
        except Exception as exc:
            response_text = f"ARIA encountered an error: {exc}"
            trace = []

    st.session_state["aria_history"].append({
        "role":    "assistant",
        "content": response_text,
        "trace":   trace,
    })
    st.session_state["aria_started"] = True
    st.rerun()


def render_aria_panel() -> None:
    """Render the ARIA chat panel with suggestion chips, chat history, and input."""
    st.markdown("---")
    st.subheader("🤖 ARIA — KPI Analyst")

    # Initialise session state
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("aria_history", [])
    st.session_state.setdefault("aria_started", False)

    # Compute badge for last response
    history = st.session_state["aria_history"]
    last_assistant = next(
        (m for m in reversed(history) if m["role"] == "assistant"), None
    )
    if last_assistant and last_assistant.get("trace"):
        trace = last_assistant["trace"]
        total_ms = sum(s.get("duration_ms", 0) for s in trace)
        st.caption(
            f"Last response: {len(trace)}/{__import__('config').AGENT_MAX_ITERATIONS} "
            f"steps  ⏱ {total_ms}ms"
        )

    # ── Suggestion chips (shown before first message) ─────────────────────
    if not st.session_state["aria_started"]:
        st.markdown("**Suggested questions:**")
        cols = st.columns(3)
        for i, chip in enumerate(_SUGGESTION_CHIPS):
            with cols[i % 3]:
                if st.button(chip, key=f"chip_{i}", use_container_width=True):
                    _handle_user_input(chip)

    # ── Chat history ──────────────────────────────────────────────────────
    for msg in st.session_state["aria_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("trace"):
                trace = msg["trace"]
                with st.expander(f"🔍 Show reasoning trace ({len(trace)} steps)"):
                    for step in trace:
                        status  = step.get("status", "")
                        icon    = ("🟢" if status == "success"
                                   else "🔴" if status == "error"
                                   else "🟡")
                        tool    = step.get("tool_name", "?")
                        dur     = step.get("duration_ms", 0)
                        st.info(
                            f"{icon} Step {step.get('step', 0) + 1}: "
                            f"**{tool}** | "
                            f"Status: {status} | {dur}ms"
                        )

    # ── ARIA Health sidebar ───────────────────────────────────────────────
    with st.sidebar.expander("🤖 ARIA Health"):
        try:
            stats = agent_store.get_agent_health_stats()
            st.metric("Avg steps/query",  stats.get("avg_steps_per_query", 0))
            st.metric("Empty result rate", f"{stats.get('empty_result_rate', 0)}%")
            st.metric("Avg latency (ms)",  stats.get("avg_response_latency_ms", 0))
            st.metric("G1 hits (max iter)", stats.get("guardrail_g1_hits", 0))
            st.metric("G2 hits (48h cap)", stats.get("guardrail_g2_hits", 0))
            if stats.get("tool_call_frequency"):
                st.markdown("**Tool usage:**")
                for tool, cnt in stats["tool_call_frequency"].items():
                    st.caption(f"  {tool}: {cnt}")
        except Exception as exc:
            st.caption(f"Stats unavailable: {exc}")

    # ── Chat input ────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask ARIA about your KPIs..."):
        _handle_user_input(prompt)
