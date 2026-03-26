# Team LG_TDS_ENT

## Participants

- LG_TDS_ENT@infosys.com

- Name (role(s) played today)

- Name (role(s) played today)

## Scenario

Scenario <#>: <title>

## What We Built

ARIA (Automated Root-cause & Insights Analyst) is a fully self-contained STB KPI Monitoring and Agentic Analysis application. It combines a real-time background data engine with an embedded AI analyst that answers natural language questions about device health.

The system has two integrated subsystems: a Background Data Engine that continuously generates and stores realistic STB telemetry (error rates, crash rates, CPU/memory utilization) in SQLite as 5-minute aggregated timeseries, and a Streamlit Dashboard with ARIA — a ReAct agent that reads from the same SQLite store.

The dashboard runs three live monitoring panels, a KPI Analyzer for pre/post change comparison, and the ARIA chat interface. The mock LLM is wired against the real Anthropic SDK interface — switching to the real Claude API requires one config change and no code rewrites.

## Challenges Attempted

| # | Challenge | Status | Notes |
|---|---|---|---|
| 1 | The <name> | done / partial / skipped | |
| 2 | | | |

## Key Decisions

**1. SQLite as the single shared state store (not in-memory or external DB)**
Every component — the data engine, panels, agent, and memory — reads and writes the same `stb_metrics.db`. This eliminated all inter-process communication complexity and made the app fully self-contained with zero infrastructure dependencies. The tradeoff is single-writer discipline: only the background engine writes to `metrics`; everything else is read-only. We enforced this at the application layer rather than DB-level constraints.

**2. Mock LLM wired to the exact Anthropic SDK interface**
Rather than hardcoding fake responses, `mock_llm.py` exposes `create(model, max_tokens, system, messages, tools)` with identical signature to the real SDK. The entire ReAct loop, tool dispatch, memory, and observability are unaware of whether they're talking to the mock or real Claude. The switch is one config line (`USE_MOCK_LLM = False`). This meant we could build and demo a complete agentic system without an API key, while keeping the production upgrade path trivially simple.

**3. ReAct loop with standard Anthropic tool-use schema, not a custom protocol**
We used the exact `tool_use` / `tool_result` message format from the Anthropic API spec. This was more work up front but means swapping in real Claude produces identical reasoning traces — no adapter layer needed. The mock synthesizes responses by reading actual tool results from conversation history rather than generating hardcoded strings.

**4. Three pre-wired demo anomalies injected at seed time**
Instead of waiting for organic spikes to appear, we inject known anomalies (DRM outage on Apollo, OOM crash wave on EOS, CPU spike on Horizon) at deterministic time offsets relative to the seed window. This makes every demo session tell the same story — the KPI Analyzer, anomaly detection, and ARIA all surface the same events reproducibly.

**5. `config.py` as the single source of truth for all constants**
Platform names, error codes, baselines, thresholds, anomaly definitions — nothing is hardcoded outside `config.py`. Every layer imports from config. This made it possible to add a new platform or change a threshold in one place and have it propagate through the generator, panels, agent tools, and guardrails automatically.

## How to Run It

```bash
# Install dependencies (Python 3.10+ required)
pip install -r requirements.txt

# Launch
streamlit run app.py
```

On first launch the app seeds 24 hours of historical data (~15 seconds), starts the background engine, then opens the dashboard at http://localhost:8501.

## If We Had Another Day

**1. Real Claude API integration and prompt tuning**
The mock intent router works well for the demo scenarios but is regex-based. With a real API key we'd validate that Claude's tool selection and response quality match or exceed the mock, then tune the system prompt for better citation formatting and more nuanced root-cause suggestions.

**2. Proper multi-tool parallel dispatch in the ReAct loop**
Currently each iteration handles one tool call before looping. The Anthropic API can return multiple `tool_use` blocks in a single response. We handle the list but the mock always emits one call at a time. A real Claude backend would sometimes request `resolve_time_reference` and `get_current_snapshot` in the same turn — we'd validate and stress-test that path.

**3. Streaming ARIA responses**
Right now the ARIA panel shows a spinner until `run_agent()` returns the full text. With `anthropic.stream()` we could render tokens as they arrive, making long comparison answers feel much more responsive.

**4. Auto-refresh without full page rerun**
The current live refresh calls `st.rerun()` on a timer which re-renders the entire app. We'd replace this with `streamlit-autorefresh` or targeted `st.empty()` container updates so the ARIA chat history doesn't flicker during panel refreshes.

**5. Persistent demo reset button**
`reset_db()` exists but isn't surfaced in the UI. A sidebar "Reset Demo" button that drops and re-seeds the database would make repeated demos cleaner. The seed flag check already makes it idempotent — it just needs a UI trigger.

**6. Alert webhook / Slack integration for background anomaly scan**
The background `anomaly_scan` job already writes findings to `agent_memory`. One more step would push critical-severity findings to a Slack webhook or PagerDuty, turning ARIA from a reactive Q&A tool into a proactive alerting system.

## How We Used Claude Code

**What we used it for**
We used Claude Code as the primary implementation engine for the entire project. We authored three specification files — `CLAUDE.md` (build instructions), `SKILLS.md` (skill-by-skill implementation rules), and `ARIA_META_PROMPT.md` (full system spec) — and then asked Claude Code to build the application from those specs in strict layer-by-layer order: storage → ingest → agent → panels → UI → app entrypoint.

**Where it saved the most time**
The biggest time savings were in the boilerplate-heavy layers. The SQLite schema, the `metrics_store.py` query functions with proper `executemany()` and `?` parameterization, the `agent_store.py` short-term/long-term memory functions, and all the Plotly chart construction were produced correctly on the first pass. Writing that by hand would have taken hours; Claude Code produced it in minutes while respecting every constraint in the spec (no f-strings in SQL, INSERT OR REPLACE, context managers everywhere).

**What worked particularly well**
The spec-driven approach was very effective. Because `CLAUDE.md` defined explicit acceptance criteria (`python -c "... assert count >= 25000"`), Claude Code could verify its own output at each step before moving on. The build order (Step 1 → 7) kept it from building on broken foundations. The naming rules and "never hardcode outside config.py" constraint were followed consistently across all 31 files without prompting.

**What surprised us**
The mock LLM came out more capable than expected. The `synthesize_response()` function that builds grounded answers from tool results in conversation history — rather than hardcoded strings — produced genuinely useful natural language output without a real model. The intent routing regex table covered the core demo scenarios accurately.

**Where we had to intervene**
One bug required a manual fix: the `T-Nh` anomaly time reference resolver was computing `seed_start + N hours` instead of `seed_end - N hours`, which placed anomaly windows in the wrong part of the seeded history (showing the spike at T+20h instead of T−4h). Once identified, the fix was a one-line change to `anomaly_injector.py`. The serialization of `ToolUseBlock` dataclasses to JSON for conversation history also needed a small fix in `agent_core.py`.

**Honest assessment**
Claude Code is most powerful when the specification is precise and the acceptance criteria are testable. The CLAUDE.md and SKILLS.md documents were the real investment — they took longer to write than the code took to generate. The payoff was that we got a working, tested, 31-file application in a single session.
