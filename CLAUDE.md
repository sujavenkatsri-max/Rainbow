# CLAUDE.md — Build Instructions for ARIA STB KPI Analyzer

This file contains all instructions for Claude Code when building, running, debugging, and extending the ARIA STB KPI Analyzer application. Read this file completely before writing any code.

---

## Project Summary

You are building a **fully self-contained, end-to-end STB (Set-Top Box) KPI Monitoring and Agentic Analysis application** called ARIA. It has two integrated subsystems:

1. **Background Data Engine** — continuously generates and stores realistic STB device telemetry (error rates, crash rates, CPU/memory utilization) in SQLite as 5-minute aggregated timeseries records, seeding 24 hours of history on first launch.

2. **Streamlit Dashboard + ARIA Agent** — displays three live monitoring panels, provides a KPI Analyzer/Validator for pre/post change comparison, and embeds ARIA, a ReAct agent that reads from the same SQLite store and answers natural language questions about the metrics.

Both subsystems share `stb_metrics.db`. The background engine is the **sole writer**. All panels and the agent are **read-only**.

**API key situation**: No Anthropic API key is available. The agent is built against the real Claude SDK interface but uses `mock_llm.py` as an internal simulation. Setting `USE_MOCK_LLM = False` in `config.py` + providing an API key is the only change needed to go live.

---

## Build Order

Build in this exact sequence. Do not skip ahead. Each step must be working before proceeding to the next.

### Step 1 — Project Scaffold
1. Create the directory structure as defined in `ARIA_META_PROMPT.md` Section 5
2. Create empty `__init__.py` in every package directory
3. Create `requirements.txt` with all dependencies (see Dependencies section below)
4. Create `config.py` with all values from `ARIA_META_PROMPT.md` Section 10

### Step 2 — Storage Layer
1. Build `storage/db_init.py` — all `CREATE TABLE IF NOT EXISTS` statements and indexes from the DDL in Section 6.8 of the meta prompt
2. Build `storage/metrics_store.py` — all metric read/write functions
3. Build `storage/agent_store.py` — agent conversation, memory, and trace read/write functions
4. **Test**: run `python -c "from storage.db_init import init_db; init_db(); print('DB OK')"` — must print `DB OK` with no errors

### Step 3 — Background Data Engine
Build in this sub-order:
1. `ingest/schema.py` — `MetricRecord` dataclass
2. `ingest/metric_generator.py` — core generation logic for all platforms × all codes
3. `ingest/seed_data.py` — historical 24h seed function
4. `ingest/anomaly_injector.py` — demo spike injection
5. `ingest/scheduler.py` — APScheduler wiring
6. **Test**: run `python -c "from ingest.seed_data import run_seed; run_seed(); print('Seed OK')"` — must print `Seed OK` and populate the metrics table with at least 20,000 rows

### Step 4 — Agent Layer
Build in this sub-order:
1. `agent/tool_definitions.py` — JSON tool schemas (7 tools)
2. `agent/agent_tools.py` — all 7 tool implementations reading from SQLite
3. `agent/agent_memory.py` — short-term and long-term memory functions
4. `agent/agent_observability.py` — trace logging and health stats
5. `agent/mock_llm.py` — internal Claude API simulation
6. `agent/agent_core.py` — ReAct loop orchestrator
7. **Test**: run `python -c "from agent.agent_core import run_agent; r,t = run_agent('What are the current error rates?', 'test-session'); print(r[:100])"` — must return a non-empty string

### Step 5 — Panels and Analyzer
1. `panels/error_rate_panel.py`
2. `panels/crash_rate_panel.py`
3. `panels/resource_panel.py`
4. `analyzer/kpi_comparator.py`
5. `analyzer/report_generator.py`

### Step 6 — UI Components
1. `ui/filters.py`
2. `ui/time_slider.py`
3. `ui/aria_panel.py`
4. `ui/dashboard.py`

### Step 7 — App Entrypoint
1. `app.py` — startup sequence, layout assembly
2. **Test**: `streamlit run app.py` — app must open, panels must render with data, ARIA input must accept a message

---

## File-by-File Implementation Rules

### `config.py`
- Must be the single source of truth for all constants
- Never hardcode values that appear in config.py anywhere else — always import from config
- `DEMO_MODE = True` by default for hackathon
- `USE_MOCK_LLM = True` by default — never set to False unless ANTHROPIC_API_KEY is set

### `storage/db_init.py`
- Use `CREATE TABLE IF NOT EXISTS` — never `DROP TABLE`
- All indexes must use `CREATE INDEX IF NOT EXISTS`
- Call `init_db()` as the very first thing in `app.py` before any other import-time side effects
- Use `sqlite3.connect(config.SQLITE_DB_PATH)` with `check_same_thread=False` for multi-thread access
- Wrap every connection in a context manager: `with sqlite3.connect(...) as conn:`

### `storage/metrics_store.py`
- All SQL must be parameterized — use `?` placeholders, never f-strings or `.format()` for SQL
- All bulk inserts must use `executemany()` — never loop with individual `execute()` calls
- Expose these functions at minimum:
  - `insert_metric_batch(records: list[MetricRecord]) -> None`
  - `query_metrics(metric_type, platforms, codes, start_time, end_time) -> list[dict]`
  - `get_available_time_range() -> tuple[str, str]`
  - `get_latest_timestamp() -> str`
  - `purge_old_metrics(hours: int) -> int`
  - `is_seeded() -> bool`
  - `mark_seeded() -> None`

### `ingest/metric_generator.py`
- Must generate records for every combination: 4 platforms × (8 error + 8 crash + 6 resource) = 88 records per tick
- Timestamp must always be snapped to 5-min boundary using `snap_to_5min()`
- `stb_count` must never be 0 or negative — use `max(1, value)`
- `event_count` must never be negative — use `max(0, value)`
- `rate_per_1000` must always be recomputed as `(event_count / stb_count) * 1000` — never store a pre-computed value from outside this formula
- Apply `PLATFORM_SCALE` multipliers to stb_count
- Apply `time_of_day_factor()` to base rates
- Apply anomaly multipliers from `anomaly_injector.py` when timestamp falls in anomaly window

### `ingest/seed_data.py`
- Check `is_seeded()` first — if already seeded, return immediately without generating data
- Seed start: `datetime.now() - timedelta(hours=config.HISTORICAL_SEED_HOURS)`
- Seed end: `datetime.now() - timedelta(minutes=5)`
- Generate in chronological order, batch insert every 12 timestamps (1 hour) to avoid memory pressure
- Call `anomaly_injector.apply_to_dataframe()` on each batch before inserting
- Call `mark_seeded()` after successful completion
- Show progress: print to console every 50 timestamps processed

### `ingest/anomaly_injector.py`
- Anomaly events are defined in a list of dicts (see meta prompt Section 6.6)
- `ANOMALY_EVENTS` time references use `"T-Nh"` format where T = seed_start_time
- Resolve all time references to absolute datetime at injection time, not at define time
- Multiplier applied to `event_count`, then `rate_per_1000` recomputed
- If `config.ANOMALY_INJECTION_ENABLED = False`, `apply_to_record()` must be a no-op passthrough

### `ingest/scheduler.py`
- Use `APScheduler BackgroundScheduler` — not `threading.Timer` or `time.sleep` loops
- Scheduler must start in daemon mode so it stops when the main process exits
- `generate_and_store_live_batch()` generates one tick at `datetime.now()` snapped to 5-min
- `run_background_anomaly_scan()` calls `detect_anomalies` tool for the last 30 minutes on all platforms and writes results to agent_memory
- `purge_old_metrics()` deletes records older than `config.DATA_RETENTION_HOURS`

### `agent/tool_definitions.py`
- Contains `TOOL_DEFINITIONS` as a Python list of dicts in the exact Anthropic tool schema format
- This same list is passed to both `mock_llm.create()` and the real `anthropic.client.messages.create()`
- Never duplicate tool schemas — import `TOOL_DEFINITIONS` wherever needed

### `agent/agent_tools.py`
- Every tool must return the standard envelope: `{"status": "ok"|"empty"|"error", "data": ..., "meta": {...}}`
- `meta` must always include: `tool_name`, `execution_time_ms`, `row_count`, `time_range`
- Every tool call must be wrapped in try/except — exceptions become `{"status": "error", "reason": str(e)}`
- `query_metrics` must reject time ranges > 48h (Guardrail G2)
- `detect_anomalies` baseline window = 24h prior to `start_time` (not full DB history)
- `compare_kpi_windows` must handle `float('inf')` → convert to `"+inf%"` string before returning
- All tools must call `log_trace()` from `agent_observability.py` before returning

### `agent/mock_llm.py`
- Must expose `create(model, max_tokens, system, messages, tools)` with identical signature to `anthropic.client.messages.create()`
- Return type is `MockMessage` dataclass — must have `.content`, `.role`, `.stop_reason`
- Tool use blocks in `.content` must have `.type="tool_use"`, `.name`, `.id`, `.input`
- Text blocks in `.content` must have `.type="text"`, `.text`
- Include at top of file: `# HACKATHON MODE: Replace with real Anthropic SDK when USE_MOCK_LLM=False`
- `synthesize_response()` must produce a natural-language answer by reading tool results from conversation history — not a hardcoded string
- Never raise exceptions — return a graceful `end_turn` text response for any unhandled case

### `agent/agent_core.py`
- `run_agent(user_message, session_id)` is the only public function
- Must respect `config.AGENT_MAX_ITERATIONS` (Guardrail G1)
- Conversation history passed to mock_llm must always be the full list — never truncate mid-turn
- Short-term memory trim (20 turns) applies only between turns — never inside a ReAct loop
- Tool results appended to history use exact schema:
  ```python
  {"role": "user", "content": [{"type": "tool_result",
                                 "tool_use_id": block.id,
                                 "content": json.dumps(result)}]}
  ```
- Always persist updated conversation history after `end_turn`
- Returns `tuple[str, list]` — (response_text, trace_steps)

### `panels/error_rate_panel.py`
- Function signature: `render_error_panel(filters: FilterState) -> None`
- Inline filter row must use `st.columns([3, 0.8, 1])` — code multiselect, All/None buttons, aggregation toggle
- Inline filter state stored in `st.session_state` under keys `panel1_codes` and `panel1_agg`
- Chart must use Plotly `go.Figure` with one `go.Scatter` trace per selected error code
- Apply color grouping: Playback = blue, DRM = red, System = orange
- Render summary table below chart showing latest window values with delta indicators (↑ ↓ →)
- If query returns no data, render `st.info("No data available for selected filters")` — never raise

### `panels/crash_rate_panel.py`
- Function signature: `render_crash_panel(filters: FilterState) -> None`
- Chart: `go.Bar` (barmode='stack') per crash code + `go.Scatter` overlay for totals on secondary Y-axis
- CRR_3006 always renders in `#ef4444` regardless of stack position
- Call `detect_crash_storm()` before rendering — show `st.warning()` banner if triggered
- Top 3 crash codes by event_count rendered in summary section

### `panels/resource_panel.py`
- Function signature: `render_resource_panel(filters: FilterState) -> None`
- CPU metrics on `yaxis`, memory metrics on `yaxis2`
- Add threshold bands via `fig.add_hrect()` for CPU warning (80%) and critical (90%)
- Add thermal throttle shading via `fig.add_vrect()` for each throttle event timestamp
- CPU_P95 trace must use `line=dict(dash='dash')` to distinguish from CPU_AVG

### `analyzer/kpi_comparator.py`
- `compare_windows(window_a, window_b, scope, platform)` returns a Pandas DataFrame
- Aggregation: SUM for `stb_count`/`event_count`, MEAN for `rate_per_1000` and resource values
- Status classification uses `HIGHER_IS_WORSE` / `HIGHER_IS_BETTER` lists from meta prompt Section 7.6
- Stable threshold: `abs(pct_change) < 5%`
- Never raise on divide-by-zero — return `float('inf')` which is serialized as `"+inf%"` in report

### `ui/aria_panel.py`
- Session ID generated once per session: `st.session_state.setdefault("session_id", str(uuid.uuid4()))`
- Suggestion chips rendered only when `st.session_state.aria_started` is False
- Chat history stored in `st.session_state.aria_history` as list of `{role, content, trace?}` dicts
- Each assistant message has an expandable reasoning trace section
- Trace steps rendered with color indicator: 🟢 success / 🔴 error / 🟡 empty_result
- Iteration badge and latency badge rendered in the subheader line after each response

### `app.py`
- First line of logic must be `from storage.db_init import init_db; init_db()`
- Startup sequence:
  1. `init_db()`
  2. Check `is_seeded()` → if False: show spinner, run `seed_data.run_seed()`, run `anomaly_injector.apply_demo_anomalies()`
  3. `scheduler.start_background_engine()` — call only once, guard with `st.session_state`
  4. Render sidebar filters → build `FilterState`
  5. Render `render_error_panel(filters)`
  6. Render `render_crash_panel(filters)`
  7. Render `render_resource_panel(filters)`
  8. Render KPI Analyzer section
  9. Render `render_aria_panel()`
- Auto-refresh: use `time.sleep` + `st.rerun()` inside a thread, or use `streamlit-autorefresh` package
- Never call `scheduler.start_background_engine()` more than once — use `st.session_state` guard:
  ```python
  if "scheduler_started" not in st.session_state:
      scheduler.start_background_engine()
      st.session_state.scheduler_started = True
  ```

---

## Dependencies (`requirements.txt`)

```
streamlit>=1.32.0
plotly>=5.18.0
pandas>=2.0.0
apscheduler>=3.10.0
pytz>=2024.1
python-dateutil>=2.9.0
reportlab>=4.0.0
```

**Do not add** `anthropic` to requirements — it is not needed in mock mode. If the user switches to real API mode, they will install it separately.

---

## Data Flow Verification Checklist

Before saying any component is complete, verify:

### Background Engine
- [ ] `metrics` table has ≥ 20,000 rows after seed
- [ ] Records exist for all 4 platforms
- [ ] Records exist for all 8 error codes, 8 crash codes, 6 resource codes
- [ ] All timestamps are aligned to 5-minute boundaries (seconds = 0, minute % 5 = 0)
- [ ] No negative `stb_count` or `event_count` values
- [ ] `rate_per_1000` = `(event_count / stb_count) * 1000` within 0.01 tolerance for every row
- [ ] Anomaly spike visible for ERR_2003 on Apollo in the T-4h to T-2h window
- [ ] Live tick adds new rows every 10 seconds in DEMO_MODE

### ARIA Agent
- [ ] `get_current_snapshot` returns data (not empty) when DB is seeded
- [ ] `compare_kpi_windows` with valid window A/B returns at least one row
- [ ] `detect_anomalies` finds the injected DRM spike (ERR_2003, Apollo)
- [ ] `resolve_time_reference("3 PM")` returns timestamps snapped to 5-min boundary
- [ ] ReAct loop terminates — never runs forever
- [ ] Conversation history persists across multiple questions in the same session
- [ ] Trace expander shows correct number of steps

### Panels
- [ ] Panel 1 renders with data when DB is seeded and no filters are changed
- [ ] Changing inline code filter updates only Panel 1 chart, not Panel 2 or 3
- [ ] Panel 3 shows both CPU (left axis) and memory (right axis)
- [ ] Crash storm banner appears when CRR_3006 injected anomaly window is in view

---

## Error Handling Rules

1. **Every database query** must be in try/except — on exception, log to console and return empty list (never propagate to Streamlit render)
2. **Every panel render function** must catch all exceptions and display `st.error("Panel unavailable: {error}")` — never crash the whole app
3. **Every agent tool** must catch all exceptions and return `{"status": "error", "reason": str(e)}`
4. **Scheduler jobs** must have `misfire_grace_time=60` and `coalesce=True` to handle missed ticks gracefully
5. **SQLite connections** must always use context managers — never call `.close()` manually

---

## Naming & Style Rules

1. All Python files use `snake_case`
2. All functions use `snake_case`
3. All Streamlit session state keys use `snake_case` with module prefix: `panel1_codes`, `aria_history`, `scheduler_started`
4. All SQL column names use `snake_case`
5. Timestamps always stored and compared as ISO 8601 strings (`"2025-03-26T14:05:00"`) — never as Unix epochs
6. Never use global mutable variables for state — use SQLite or `st.session_state`
7. Imports at top of file only — no inline imports
8. Every function that queries SQLite must have a docstring stating what it returns and what parameters are SQL-injected vs safe

---

## Testing Each Component (Quick Smoke Tests)

Run these in order after building each step:

```bash
# Step 2: DB
python -c "from storage.db_init import init_db; init_db(); print('DB OK')"

# Step 3: Seed
python -c "
from storage.db_init import init_db
init_db()
from ingest.seed_data import run_seed
run_seed()
from storage.metrics_store import query_metrics
from datetime import datetime, timedelta
end = datetime.now().isoformat()
start = (datetime.now() - timedelta(hours=24)).isoformat()
rows = query_metrics('error_rate', ['Apollo'], ['all'], start, end)
print(f'Seed OK — {len(rows)} error rate rows for Apollo')
"

# Step 4: Agent
python -c "
from storage.db_init import init_db; init_db()
from ingest.seed_data import run_seed; run_seed()
from agent.agent_core import run_agent
r, t = run_agent('What are the current error rates on Apollo?', 'smoke-test')
print(f'Agent OK — response: {r[:120]}')
print(f'Trace steps: {len(t)}')
"

# Step 7: Full app
streamlit run app.py
```

---

## Switching to Real Claude API

When the user has an API key and wants to use real Claude:

1. In `config.py`:
   ```python
   USE_MOCK_LLM      = False
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

2. In `requirements.txt`, add:
   ```
   anthropic>=0.25.0
   ```

3. In `agent/mock_llm.py`, the `create()` function routes based on config:
   ```python
   import anthropic
   import config

   def create(model, max_tokens, system, messages, tools):
       if config.USE_MOCK_LLM:
           return _mock_create(model, max_tokens, system, messages, tools)
       else:
           client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
           return client.messages.create(
               model=model, max_tokens=max_tokens,
               system=system, messages=messages, tools=tools
           )
   ```

No other code changes required. The ReAct loop, tool dispatch, memory, and observability all work identically.

---

## What NOT to Do

- **Never** write SQL with f-strings or `.format()` — always use `?` parameterized queries
- **Never** use `st.experimental_rerun()` — use `st.rerun()`
- **Never** call `scheduler.start()` more than once — it will create duplicate background jobs
- **Never** write to the `metrics` table from any panel, analyzer, or agent code — only `metric_generator.py` and `seed_data.py` may write to it
- **Never** store large DataFrames in `st.session_state` — store only primitive values and IDs
- **Never** use `import *` — always explicit imports
- **Never** leave the seed step out of the startup sequence — panels will render empty without it
- **Never** hardcode platform names, error codes, or thresholds anywhere outside `config.py`
- **Never** generate fake responses in `mock_llm.py` — `synthesize_response()` must read from actual tool results in conversation history
- **Never** use `localStorage` or browser storage — all state lives in SQLite or `st.session_state`

---

## Demo Scenario (Use This to Verify End-to-End)

1. `streamlit run app.py`
2. Wait for seed progress to complete ("Seeding 24h of data...")
3. All three panels should render immediately with populated charts
4. Set sidebar Platform = Apollo, Time Range = Last 6h
5. Panel 1 should show an elevated spike for ERR_2003 (DRM failures) — the injected anomaly
6. Scroll to KPI Analyzer → Window vs Window
7. Set Window A = T-4h to T-2h (pre-spike), Window B = T-2h to T-now (post-spike)
8. Click Run Comparison → delta table must show ERR_2003 as top degraded KPI (≥200% change)
9. Scroll to ARIA → type: "What changed in error rates on Apollo in the last 4 hours?"
10. ARIA should call `resolve_time_reference` → `compare_kpi_windows` → return explanation citing ERR_2003 spike
11. Expand reasoning trace → shows all 3 tool call steps with durations
12. Click "Has ERR_2003 spiked like this before?" chip → ARIA queries long-term memory and responds
