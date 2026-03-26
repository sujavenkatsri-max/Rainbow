# SKILLS.md — ARIA STB KPI Analyzer
## Agent Skills & Background Data Engine Skills

This file defines the complete set of skills Claude Code must implement when building the ARIA application. Each skill has a trigger, detailed behavior, implementation rules, and acceptance criteria. Skills are organized by subsystem.

---

## SUBSYSTEM A — Background Data Engine Skills

---

### Skill A1: Initialize SQLite Database

**Trigger**: User asks to set up the database, create tables, add indexes, or reset the schema.

**Behavior**:
- Create all 5 tables using `CREATE TABLE IF NOT EXISTS`: `metrics`, `seed_status`, `agent_conversation`, `agent_memory`, `agent_trace`
- Create all indexes defined in the DDL
- Expose a single `init_db()` function that is safe to call multiple times without side effects
- Expose `reset_db()` for demo resets — drops and recreates all tables

**Implementation Rules**:
- Always use `CREATE TABLE IF NOT EXISTS` — never `CREATE TABLE` or `DROP TABLE` in `init_db()`
- Use `sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False)` for multi-thread safety
- Always use context managers: `with sqlite3.connect(...) as conn:`
- Never call `.close()` manually — context manager handles it
- `reset_db()` must drop tables in reverse dependency order to avoid FK issues

**Acceptance Criteria**:
```bash
python -c "from storage.db_init import init_db; init_db(); print('OK')"
# Must print OK with no errors
# Running twice must not raise any exception
```

---

### Skill A2: Generate Live Metric Batch

**Trigger**: User asks to build the metric generator, add a new metric type, change baseline values, or fix generation logic.

**Behavior**:
- Generate exactly **88 records per tick**: 4 platforms × (8 error + 8 crash + 6 resource) = 88
- Each record is a `MetricRecord` dataclass with fields: `timestamp`, `platform`, `metric_type`, `code`, `stb_count`, `event_count`, `rate_per_1000`
- Apply Gaussian noise to baseline rates: `noise = random.gauss(0, base_rate * 0.15)`
- Apply `PLATFORM_SCALE` multipliers to `stb_count`
- Apply `time_of_day_factor()` to base rates
- Apply anomaly multipliers if current timestamp falls within an active anomaly window

**Implementation Rules**:
- `stb_count` must never be 0 or negative: `stb_count = max(1, int(value))`
- `event_count` must never be negative: `event_count = max(0, int(value))`
- `rate_per_1000` must always be recomputed: `(event_count / stb_count) * 1000` — never store externally computed values
- Timestamp must always be snapped to 5-min boundary before use:
  ```python
  def snap_to_5min(dt):
      return dt.replace(second=0, microsecond=0, minute=(dt.minute // 5) * 5)
  ```
- For resource metrics (CPU, memory), `rate_per_1000` stores the metric value directly (e.g. `55.3` for CPU_AVG %) — this is consistent with how tools read it back
- Never hardcode platform names or codes — always read from `config.PLATFORMS` and `config.CODE_REGISTRY`
- `time_of_day_factor()` must return an additive offset, not a multiplier, to allow negative (reduction) in off-peak hours

**Baseline Registry** (must be defined in `config.py`, not hardcoded in generator):
```python
CODE_BASELINES = {
    # (baseline_rate_per_1000, stb_min, stb_max)
    "ERR_2001": (2.5,  800, 1200),
    "ERR_2002": (1.2,  400,  700),
    "ERR_2003": (3.1,  600, 1000),
    "ERR_2004": (0.8,  200,  500),
    "ERR_2005": (1.5,  300,  600),
    "ERR_2006": (4.2, 1000, 1800),
    "ERR_2007": (2.0,  500,  900),
    "ERR_2008": (0.6,  150,  400),
    "CRR_3001": (0.3,  100,  300),
    "CRR_3002": (1.8,  400,  800),
    "CRR_3003": (0.5,  150,  350),
    "CRR_3004": (1.1,  300,  600),
    "CRR_3005": (0.9,  250,  500),
    "CRR_3006": (0.4,   80,  200),
    "CRR_3007": (0.2,   50,  150),
    "CRR_3008": (0.1,   30,  100),
    # Resource: (baseline_mean, baseline_std)
    "CPU_AVG":          (55.0,  8.0),
    "CPU_P95":          (72.0, 10.0),
    "MEM_FREE_AVG":    (180.0, 25.0),
    "MEM_HEAP_USED":   (320.0, 30.0),
    "MEM_SWAP_USED":    (45.0, 12.0),
    "THERMAL_THROTTLE": (50.0, 15.0),
}
```

**Acceptance Criteria**:
- Generate one batch and inspect: all 88 records present, no negatives, timestamps 5-min aligned
- `rate_per_1000` equals `(event_count / stb_count) * 1000` within 0.001 tolerance for every record

---

### Skill A3: Seed 24-Hour Historical Data

**Trigger**: User asks to build the seed function, change the seed window, or debug missing historical data in panels.

**Behavior**:
- Check `seed_status` table first — if `seeded = 1`, return immediately (idempotent)
- Generate records for every 5-min timestamp from `now() - 24h` to `now() - 5min`
- For each timestamp, call the same `generate_batch(timestamp)` used in live generation
- Apply anomaly multipliers to seeded records where timestamp falls in anomaly windows
- Insert in batches of 12 timestamps (1 hour = 1056 records per batch insert) to control memory
- Mark `seeded = 1` in `seed_status` only after full completion
- Print console progress every 50 timestamps

**Implementation Rules**:
- Use `executemany()` for batch inserts — never loop with `execute()` for individual records
- Seed must be **synchronous** (blocking) so panels don't render before data exists
- Wrap entire seed in a single try/except — if seed fails, leave `seeded = 0` so next launch retries
- Total records: 288 timestamps × 4 platforms × 22 codes = **25,344 rows minimum**
- After seed, verify: `SELECT COUNT(*) FROM metrics` must return ≥ 25,000

**Acceptance Criteria**:
```bash
python -c "
from storage.db_init import init_db; init_db()
from ingest.seed_data import run_seed; run_seed()
import sqlite3, config
conn = sqlite3.connect(config.SQLITE_DB_PATH)
count = conn.execute('SELECT COUNT(*) FROM metrics').fetchone()[0]
print(f'Rows: {count}')
assert count >= 25000, 'Insufficient seed data'
print('Seed OK')
"
```

---

### Skill A4: Inject Demo Anomalies

**Trigger**: User asks to add anomaly injection, configure demo spikes, or debug why panels don't show anomalies.

**Behavior**:
- Define `ANOMALY_EVENTS` list in config (or `anomaly_injector.py`) with 3 pre-wired events:
  - DRM Outage on Apollo: ERR_2003 + ERR_2004, T-4h to T-2h, 4.5× multiplier
  - OOM Crash Wave on EOS: CRR_3002 + CRR_3006, T-3h to T-2.5h, 3.0× multiplier
  - CPU Spike on Horizon: CPU_AVG + CPU_P95, T-1.5h to T-1h, 1.6× multiplier
- `apply_to_record(record, seed_start_time)` — if record's platform + code + timestamp match an anomaly window, multiply `event_count` by the multiplier and recompute `rate_per_1000`
- `apply_demo_anomalies()` — UPDATE existing seeded rows in `metrics` table for the anomaly windows
- If `config.ANOMALY_INJECTION_ENABLED = False`, all functions must be no-op passthroughs

**Implementation Rules**:
- Resolve `"T-Nh"` relative times to absolute datetimes using `seed_start_time` as anchor, not `datetime.now()`, to ensure anomalies appear consistently in the seeded history
- Multiplier applied to `event_count`: `event_count = int(event_count * multiplier)`
- Always recompute `rate_per_1000 = (event_count / stb_count) * 1000` after applying multiplier
- Anomaly UPDATE SQL must use parameterized queries

**Acceptance Criteria**:
- After seed + injection: query ERR_2003 on Apollo between T-4h and T-2h — `rate_per_1000` must be ≥ 3× the non-anomaly baseline
- Panel 1 must visually show a spike when Apollo is selected and time range covers the anomaly window

---

### Skill A5: Run Background Scheduler

**Trigger**: User asks to build the scheduler, fix duplicate job execution, or debug live data not updating.

**Behavior**:
- Use `APScheduler BackgroundScheduler` with 3 jobs:
  1. `metric_ingest`: calls `generate_and_store_live_batch()` every `config.INGEST_INTERVAL_SECONDS` (10s in DEMO_MODE, 300s real)
  2. `anomaly_scan`: calls `run_background_anomaly_scan()` every `config.ANOMALY_SCAN_INTERVAL_SECONDS` (120s)
  3. `data_retention`: calls `purge_old_metrics(config.DATA_RETENTION_HOURS)` every 1 hour
- `start_background_engine()` returns the running scheduler instance
- Guard in `app.py` with `st.session_state.scheduler_started` to prevent duplicate starts

**Implementation Rules**:
- All jobs must have `misfire_grace_time=60` and `coalesce=True`
- Scheduler must start in daemon mode: `BackgroundScheduler(daemon=True)`
- `generate_and_store_live_batch()` must call `snap_to_5min(datetime.now())` for the timestamp — never use raw `datetime.now()` as the record timestamp
- `run_background_anomaly_scan()` runs `detect_anomalies` for the last 30 minutes on all platforms and writes any findings to `agent_memory` table
- `purge_old_metrics()` must use `DELETE FROM metrics WHERE timestamp < datetime('now', '-{N} hours')` — never delete everything

**Guard pattern in `app.py`**:
```python
if "scheduler_started" not in st.session_state:
    scheduler.start_background_engine()
    st.session_state["scheduler_started"] = True
```

**Acceptance Criteria**:
- Wait 30 seconds after launch in DEMO_MODE — `SELECT MAX(timestamp) FROM metrics` must advance
- No duplicate rows for the same timestamp + platform + code after 60 seconds of running

---

### Skill A6: Metrics Store Read/Write

**Trigger**: User asks to build query functions, fix incorrect aggregation, or add a new query pattern.

**Behavior**:
- `insert_metric_batch(records)`: bulk insert using `executemany()`
- `query_metrics(metric_type, platforms, codes, start_time, end_time)`: returns list of dicts
- `get_available_time_range()`: returns `(min_timestamp, max_timestamp)` from metrics table
- `get_latest_timestamp()`: returns most recent timestamp string
- `purge_old_metrics(hours)`: deletes records older than N hours, returns deleted count
- `is_seeded()` / `mark_seeded()`: check and set seed_status table

**Implementation Rules**:
- All SQL uses `?` parameterized queries — never f-strings or `.format()` for SQL values
- `insert_metric_batch()` must use `executemany()` with `INSERT OR REPLACE` to handle duplicate timestamps gracefully
- `query_metrics()` must aggregate using `GROUP BY timestamp, platform, code` with `SUM(stb_count)`, `SUM(event_count)`, `AVG(rate_per_1000)` — never return raw unaggregated rows to callers
- Platform list in WHERE clause: use `IN (?,?,?)` with `','.join('?'*len(platforms))` pattern
- If `codes = ["all"]`, expand to full code list for that `metric_type` from config — never use `IN ('all')`
- Every function has a docstring stating: return type, what's SQL-safe, what's parameterized

**Acceptance Criteria**:
- Insert 88 records, query back — all 88 returned with correct aggregation
- Query with `platform=["all"]` after expanding returns data for all 4 platforms
- `purge_old_metrics(0)` removes all rows; table still exists with 0 rows

---

## SUBSYSTEM B — Streamlit Dashboard Skills

---

### Skill B1: Sidebar Global Filters

**Trigger**: User asks to build the sidebar, add a new platform, or fix filter state not persisting.

**Behavior**:
- Platform multiselect: `["All", "Apollo", "EOS", "Horizon", "Liberty"]`, default = `["All"]`
- Time range selectbox: `["Last 1h", "Last 3h", "Last 6h", "Last 12h", "Last 24h", "Custom"]`, default = `"Last 24h"`
- If Custom: render `st.date_input` + `st.time_input` for start and end
- Return a `FilterState` dataclass from `build_filter_state()` function
- Pass `FilterState` to all three panel render functions

**Implementation Rules**:
- All filter values stored in `st.session_state` with keys: `sidebar_platforms`, `sidebar_time_range`, `sidebar_custom_start`, `sidebar_custom_end`
- "All" platform selection means expand to all 4 platforms in SQL — never pass `["All"]` to a query
- `FilterState.get_time_bounds()` must return timezone-naive `datetime` objects
- `FilterState.platform_sql_list()` must return `config.PLATFORMS` when "All" is selected
- Changing any sidebar filter must trigger `st.rerun()` — achieved automatically via Streamlit reactivity; do not call `st.rerun()` manually on filter change

**Acceptance Criteria**:
- Select "Apollo" only — all three panels reload showing only Apollo data
- Select "Custom" time range — date/time pickers appear, selecting a range updates all panels

---

### Skill B2: Panel 1 — STB Error Rate Monitor

**Trigger**: User asks to build, update, or fix the error rate panel.

**Behavior**:
- Query `metrics` table for `metric_type = 'error_rate'` filtered by active platforms, selected error codes, and time range
- Render Plotly multi-line timeseries — one `go.Scatter` trace per selected error code
- Render inline filter row above the chart (code multiselect + All/None buttons + aggregation toggle)
- Render summary table below chart with latest window values and delta vs previous window

**Implementation Rules**:
- Function signature: `render_error_panel(filters: FilterState) -> None`
- Inline filter state keys: `panel1_codes` (list), `panel1_agg` (str: "rate_per_1000" | "stb_count")
- Inline filter row layout: `st.columns([3, 0.8, 1])` — multiselect, All/None buttons, aggregation toggle
- Default selected codes: all 8 ERR codes
- Color assignment (must be consistent across re-renders — use index-based lookup, not random):
  - Playback errors (ERR_2001, ERR_2002): `["#3b82f6", "#60a5fa"]`
  - DRM errors (ERR_2003, ERR_2004): `["#ef4444", "#f87171"]`
  - System errors (ERR_2005–2008): `["#f97316", "#fb923c", "#fdba74", "#fed7aa"]`
- If query returns no data: `st.info("No data for selected filters — try adjusting platform or time range")` — never raise
- Summary table: `st.dataframe()` with columns `[Code, Description, Latest Value, Previous Value, Delta, Direction]`
- Delta direction: `"↑"` if latest > previous, `"↓"` if latest < previous, `"→"` if equal

**Acceptance Criteria**:
- Panel renders without error when DB is seeded
- Deselecting all codes shows the "No data" info message
- Aggregation toggle switches Y-axis label and values correctly

---

### Skill B3: Panel 2 — STB Crash Rate Tracker

**Trigger**: User asks to build, update, or fix the crash rate panel.

**Behavior**:
- Query `metrics` table for `metric_type = 'crash_rate'` filtered by active platforms, selected crash codes, and time range
- Render Plotly stacked bar chart per crash code + total crash rate line on secondary Y-axis
- Check for crash storm before rendering and show warning banner if triggered
- Render inline filter row and summary section

**Implementation Rules**:
- Function signature: `render_crash_panel(filters: FilterState) -> None`
- Inline filter state keys: `panel2_codes`, `panel2_agg`
- Chart: `go.Bar(barmode='stack')` per code + `go.Scatter(yaxis='y2')` for totals
- CRR_3006 (Crash Loop) must always use `marker_color="#ef4444"` regardless of ordering
- Crash storm check:
  ```python
  def detect_crash_storm(df):
      recent = df[df.timestamp >= (now - timedelta(minutes=30))].event_count.sum()
      baseline = df[df.timestamp < (now - timedelta(minutes=30))].event_count.mean()
      return recent > baseline * config.CRASH_STORM_MULTIPLIER
  ```
- If crash storm: `st.warning("⚠️ Crash Storm Detected — crash rate exceeds 2× baseline in last 30 min")`
- Summary: top 3 crash codes by `event_count.sum()` for selected time range, displayed as `st.metric()` cards
- If no data: `st.info(...)` — never raise

**Acceptance Criteria**:
- CRR_3006 always renders red regardless of which other codes are selected
- Crash storm banner appears when the CRR_3002/CRR_3006 anomaly window is in view (EOS platform)
- Deselecting CRR_3006 removes it from the chart but does not affect other codes

---

### Skill B4: Panel 3 — Device Resource Utilization

**Trigger**: User asks to build, update, or fix the resource utilization panel.

**Behavior**:
- Query `metrics` table for `metric_type IN ('cpu_utilization', 'memory_utilization')`
- Render Plotly dual-axis chart: CPU metrics on left Y-axis (%), memory metrics on right Y-axis (MB)
- Add CPU threshold bands and thermal throttle vertical shading
- Render inline filter row with resource metric multiselect

**Implementation Rules**:
- Function signature: `render_resource_panel(filters: FilterState) -> None`
- Inline filter state key: `panel3_metrics` (list), default: `["CPU_AVG", "MEM_FREE_AVG"]`
- CPU metrics (`CPU_AVG`, `CPU_P95`) on `yaxis`; all memory metrics on `yaxis2`
- `CPU_P95` trace must use `line=dict(dash='dash')` — visually distinct from `CPU_AVG` (solid)
- Threshold bands:
  ```python
  fig.add_hrect(y0=80, y1=90,  fillcolor="#f59e0b", opacity=0.08, layer="below", line_width=0)
  fig.add_hrect(y0=90, y1=100, fillcolor="#ef4444", opacity=0.08, layer="below", line_width=0)
  ```
- Thermal throttle shading: for each timestamp where `THERMAL_THROTTLE rate_per_1000 > 100` (device count proxy), add:
  ```python
  fig.add_vrect(x0=ts, x1=ts_plus_5min, fillcolor="#ef4444", opacity=0.10, layer="below", line_width=0)
  ```
- Memory pressure annotation: when `MEM_FREE_AVG < config.MEM_FREE_WARNING_MB`, add a marker annotation on the chart
- If only memory metrics are selected (no CPU), hide the left Y-axis to avoid empty axis

**Acceptance Criteria**:
- Both CPU and memory display on correct axes when both types are selected
- CPU_P95 line appears dashed, CPU_AVG solid
- Thermal throttle shading appears as vertical bands when Horizon anomaly window is in view

---

### Skill B5: KPI Analyzer / Validator

**Trigger**: User asks to build, update, or fix the KPI Analyzer comparison section.

**Behavior**:
- Render 3 comparison mode options: Window vs Window, Point vs Point, Baseline vs Current
- Render appropriate time sliders for selected mode
- On "Run Comparison" click: call `kpi_comparator.compare_windows()` and render the report
- Report sections: summary banner, delta table, top movers, platform heatmap, export button

**Implementation Rules**:
- Comparison mode stored in `st.session_state.kpi_mode`
- Window sliders use `st.select_slider()` over available timestamps from `get_available_time_range()`
- Window A and Window B must not overlap — validate before enabling Run button:
  ```python
  if window_a_end >= window_b_start:
      st.error("Windows must not overlap. Window B must start after Window A ends.")
      st.stop()
  ```
- Baseline vs Current: auto-set Window A = `(now-48h, now-24h)`, Window B = current sidebar range
- Delta table: `st.dataframe(df.style.apply(color_rows, axis=1))` where:
  - Degraded rows → `background-color: #fde8e8` (light red)
  - Improved rows → `background-color: #e8fde8` (light green)
  - Stable rows → default
- Top Movers: sorted by `abs(pct_change)` descending — 3 degraded + 3 improved as `st.metric()` with delta
- Platform heatmap: visible only when `FilterState.platforms == ["All"]`
- Export button: `st.download_button(label="📥 Download CSV", data=df.to_csv(index=False), file_name=f"stb_kpi_{window_a_start}_vs_{window_b_start}.csv")`

**Acceptance Criteria**:
- Overlapping windows shows error and disables Run button
- Delta table shows Degraded rows in red for the DRM anomaly window comparison
- CSV download produces valid file with all columns

---

## SUBSYSTEM B — ARIA Agent Skills

---

### Skill C1: ReAct Loop Orchestrator

**Trigger**: User asks to build the agent core, fix infinite loops, or extend the iteration logic.

**Behavior**:
- `run_agent(user_message, session_id)` is the single public entrypoint
- Implements the ReAct cycle: Think (LLM call) → Act (tool dispatch) → Observe (append result) → loop until `end_turn` or max iterations
- Returns `(response_text: str, trace: list[dict])`

**Implementation Rules**:
- Load short-term memory at start of every call — never cache between calls
- Iteration counter increments only on `tool_use` responses — not on `end_turn`
- Tool result appended to history using exact schema:
  ```python
  {"role": "user", "content": [
      {"type": "tool_result", "tool_use_id": block.id,
       "content": json.dumps(result)}
  ]}
  ```
- On max iterations reached (Guardrail G1): compile what was gathered into a partial response:
  ```
  "Analysis incomplete — maximum reasoning steps reached.
   Based on what I found: [summarize tool results gathered so far]."
  ```
- Tool dispatch uses a registry dict: `TOOL_REGISTRY = {"query_metrics": query_metrics, ...}`
- Every tool call wrapped in try/except — exceptions produce `{"status": "error", "reason": str(e)}`
- Persist conversation history after every `end_turn` (not after each tool call — reduces DB writes)
- Always call `agent_observability.log_trace()` for every tool call step

**Acceptance Criteria**:
- Single-tool query (snapshot) completes in 1–2 iterations
- Multi-tool query (compare with time resolution) completes in 3–4 iterations
- Setting `AGENT_MAX_ITERATIONS = 1` forces partial response on any multi-step query
- Conversation persists: second question in same session has access to first question context

---

### Skill C2: Internal Claude API Simulation (`mock_llm.py`)

**Trigger**: User asks to build mock_llm, fix intent routing, or add handling for a new query pattern.

**Behavior**:
- `create(model, max_tokens, system, messages, tools)` mirrors `anthropic.client.messages.create()` exactly
- Returns `MockMessage` dataclass with `.content`, `.role`, `.stop_reason`
- Routes user messages to appropriate tools via keyword-based intent classification
- After tool results arrive: synthesizes a grounded natural-language response by reading tool results from conversation history

**MockMessage Dataclass**:
```python
@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""

@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""       # generate with uuid.uuid4()
    name: str = ""
    input: dict = field(default_factory=dict)

@dataclass
class MockMessage:
    content: list      # list of TextBlock or ToolUseBlock
    role: str = "assistant"
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use"
```

**Intent Routing Rules** (check in this priority order):
```python
INTENT_RULES = [
    # Pattern                                    Primary tool           Secondary tool
    (r"compar|differ|between|change|before.*after", "compare_kpi_windows", "resolve_time_reference"),
    (r"anomal|spike|unusual|alert|abnormal",        "detect_anomalies",    None),
    (r"\btop\b|most|worst|highest|biggest",         "get_top_movers",      None),
    (r"current|right now|latest|now\b",             "get_current_snapshot", None),
    (r"summar|overview|how is|status of",           "summarize_panel",     None),
    (r"before|happened before|recurring|again",     "get_current_snapshot", "memory_query"),
    # Time reference without explicit tool: resolve first
    (r"\d{1,2}\s*(am|pm|:)|hours? ago|morning|evening|night", "resolve_time_reference", None),
]
# Fallback: get_current_snapshot
```

**`synthesize_response()` Rules**:
- Extract all `tool_result` content blocks from conversation history for current turn
- Build response by filling a template with actual values from tool results — never generate numbers not in tool results
- Template examples:
  - compare result → "Between [window_a] and [window_b] on [platform], [top_degraded_code] increased by [pct]% — from [val_a] to [val_b] per 1000 devices."
  - snapshot result → "Current [platform] metrics: [code1] = [val1]/1000, [code2] = [val2]/1000."
  - empty result → "No data available for [metric] on [platform] between [time_a] and [time_b]."
- Never fabricate a number. If a tool returned `status: "empty"`, the response must state no data was found.

**API Swap Rule**: `mock_llm.py` must contain this routing at top:
```python
def create(model, max_tokens, system, messages, tools):
    if not config.USE_MOCK_LLM:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return client.messages.create(
            model=model, max_tokens=max_tokens,
            system=system, messages=messages, tools=tools
        )
    return _mock_create(model, max_tokens, system, messages, tools)
```

**Acceptance Criteria**:
- `MockMessage` has identical attribute access pattern as `anthropic.types.Message`
- Sending "What are current error rates?" returns a `tool_use` response with `get_current_snapshot`
- Sending "Compare error codes between 3 PM and 5 PM" returns `tool_use` for `resolve_time_reference` first
- After tool results are in history, next call returns `end_turn` with a grounded text response

---

### Skill C3: Tool — `query_metrics`

**Trigger**: User asks to build or fix the query_metrics tool.

**Behavior**:
- Query the `metrics` table and return filtered, aggregated timeseries records
- Enforces Guardrail G2: reject time ranges > 48 hours

**Implementation**:
```python
def query_metrics(metric_type, platform, codes, start_time, end_time):
    # G2: time range cap
    duration = (parse(end_time) - parse(start_time)).total_seconds()
    if duration > 172800:  # 48 hours
        return {"status": "error", "reason": "time_range_exceeds_48h_limit",
                "meta": {"tool_name": "query_metrics", ...}}

    platforms = config.PLATFORMS if platform == "all" else ([platform] if isinstance(platform, str) else platform)
    code_list  = get_codes_for_type(metric_type) if codes == ["all"] else codes

    sql = """
        SELECT timestamp, platform, metric_type, code,
               SUM(stb_count)     AS stb_count,
               SUM(event_count)   AS event_count,
               AVG(rate_per_1000) AS rate_per_1000
        FROM metrics
        WHERE metric_type = ?
          AND platform   IN ({p})
          AND code       IN ({c})
          AND timestamp  >= ?
          AND timestamp  <= ?
        GROUP BY timestamp, platform, code
        ORDER BY timestamp ASC
    """.format(p=','.join('?'*len(platforms)), c=','.join('?'*len(code_list)))
```

**Implementation Rules**:
- Return standard envelope: `{"status": "ok"|"empty"|"error", "data": [...], "meta": {...}}`
- `meta` must include: `tool_name`, `execution_time_ms`, `row_count`, `time_range`
- If `codes == ["all"]`: expand using `get_codes_for_type(metric_type)` — never pass literal `"all"` to SQL
- Call `log_trace()` before returning

**Acceptance Criteria**:
- Returns `status: "empty"` (not error) when valid query returns zero rows
- Returns `status: "error"` with reason when time range > 48h
- Returns aggregated rows (GROUP BY applied) — not raw per-insert rows

---

### Skill C4: Tool — `compare_kpi_windows`

**Trigger**: User asks to build or fix the comparison tool.

**Behavior**:
- Compute delta between Window A and Window B for all matching KPIs
- Return delta records with: code, metric_type, platform, value_a, value_b, delta, pct_change, status

**Implementation Rules**:
- Aggregate each window to one representative value per (code, platform):
  - Counts (`stb_count`, `event_count`): SUM across window
  - Rates/utilization (`rate_per_1000`): MEAN across window
- `pct_change` computation:
  ```python
  if value_a == 0 and value_b == 0:  pct_change = 0.0
  elif value_a == 0:                  pct_change = float('inf')
  else:                               pct_change = (delta / value_a) * 100
  ```
- Convert `float('inf')` to string `"+inf%"` before JSON serialization — never let infinity propagate
- Status classification uses `HIGHER_IS_WORSE` list from config — never hardcode in this function
- Sort output by `abs(pct_change)` descending

**Acceptance Criteria**:
- Window A = normal period, Window B = anomaly period → ERR_2003 shows Degraded with large pct_change
- `value_a = 0`, `value_b = 5.0` → `pct_change = "+inf%"`, no exception raised
- Both windows returning same values → `status = "Stable"`

---

### Skill C5: Tool — `detect_anomalies`

**Trigger**: User asks to build or fix the anomaly detection tool.

**Behavior**:
- Compute z-score for each metric in the inspection window against a 24h rolling baseline
- Return anomaly records with: timestamp, code, platform, observed, baseline_mean, z_score, severity
- Write findings to `agent_memory` table

**Implementation Rules**:
- Baseline window: `start_time - 24h` to `start_time` — not full DB history
- Per code+platform: compute `mean` and `std` of `rate_per_1000` across baseline window
- Skip codes where `std == 0` (constant baseline — no meaningful z-score)
- Z-score: `(observed - baseline_mean) / baseline_std`
- Severity: `"critical"` if `abs(z) >= config.ANOMALY_ZSCORE_CRITICAL (3.0)`, else `"warning"` if `abs(z) >= config.ANOMALY_ZSCORE_WARNING (2.0)`
- Write to `agent_memory` only for anomalies with severity = critical or warning:
  ```python
  agent_memory.write_memory(metric_type, code, platform,
      f"z-score={z:.1f}, observed={observed:.1f}, baseline={mean:.1f}", severity)
  ```
- Dedup before writing: skip if same (code, platform, 30-min bucket) already in `agent_memory`

**Acceptance Criteria**:
- Run on Apollo ERR_2003 during injected anomaly window → returns at least one critical anomaly
- Run on baseline-only period → returns empty result (no false positives)
- `agent_memory` table has entries after running on anomaly window

---

### Skill C6: Tool — `get_top_movers`

**Trigger**: User asks to build or fix the top movers tool.

**Behavior**:
- Internally calls `compare_kpi_windows` and sorts results by `abs(pct_change)` descending
- Filters by `direction`: "degraded" | "improved" | "both"
- Returns top N results

**Implementation Rules**:
- Reuse `compare_kpi_windows` — never duplicate comparison logic here
- Exclude `status = "Stable"` entries from results
- Handle `"+inf%"` as sortable: treat as `float('inf')` for sorting purposes only — convert back to string in output
- `top_n` defaults to 5, accepts 1–20

**Acceptance Criteria**:
- `direction="degraded"` returns only Degraded-status KPIs
- `direction="improved"` returns only Improved-status KPIs
- Results sorted by abs magnitude — highest change first

---

### Skill C7: Tool — `get_current_snapshot`

**Trigger**: User asks to build or fix the snapshot tool.

**Behavior**:
- Return the most recent 5-minute window values for requested KPIs and platform

**Implementation Rules**:
- Get latest timestamp: `SELECT MAX(timestamp) FROM metrics`
- Query only that single timestamp bucket — not a range
- If `codes = ["all"]`: query all codes for all metric types
- Group by platform and code for the latest timestamp

**Acceptance Criteria**:
- Returns data immediately after seed
- `platform="all"` returns data for all 4 platforms
- Returns single-timestamp data — not a timeseries

---

### Skill C8: Tool — `resolve_time_reference`

**Trigger**: User asks to build or fix time reference resolution, or adds a new time expression pattern.

**Behavior**:
- Convert natural language time references to absolute ISO 8601 start/end timestamps
- Snap all results to 5-minute boundaries

**Pattern Registry** (must handle all of these):
```python
PATTERNS = {
    r"(\d{1,2})\s*(am|pm)":           parse_12h,        # "3 PM", "11am"
    r"(\d{1,2}):(\d{2})\s*(am|pm)?":  parse_hmm,        # "14:00", "3:30 PM"
    r"(\d+)\s*h(?:ours?)?\s*ago":     hours_ago,         # "2 hours ago", "3h ago"
    r"(\d+)\s*min(?:utes?)?\s*ago":   minutes_ago,       # "30 minutes ago"
    r"this\s+morning":                morning_today,      # 06:00–12:00 today
    r"this\s+afternoon":              afternoon_today,    # 12:00–17:00 today
    r"this\s+evening":                evening_today,      # 17:00–21:00 today
    r"last\s+night":                  last_night,         # 20:00–00:00 yesterday
    r"yesterday":                     yesterday_range,    # 00:00–23:59 yesterday
    r"today":                         today_range,        # 00:00–now today
}
```

**Implementation Rules**:
- For point references (single time like "3 PM"): `start = snap(3pm), end = snap(3pm) + timedelta(minutes=5)`
- For range references (like "this morning"): return full range snapped at both ends
- `anchor` parameter defaults to `datetime.now()` — use it for relative calculations
- Always return: `{"start": iso_str, "end": iso_str, "label": human_readable_str, "type": "point"|"range"}`
- If no pattern matches: return `{"status": "error", "reason": "unrecognized_time_reference"}`

**Acceptance Criteria**:
- `"3 PM"` → start and end both snap to `15:00:00` and `15:05:00`
- `"2 hours ago"` → start = now minus 2h snapped, end = now snapped
- `"this morning"` → start = `06:00:00` today, end = `12:00:00` today
- Unrecognized input → error status, no exception raised

---

### Skill C9: Tool — `summarize_panel`

**Trigger**: User asks to build or fix the panel summary tool.

**Behavior**:
- Generate a structured summary for one panel including trend direction, top codes, active alerts, and a plain-language narrative
- Uses only data from the local SQLite store

**Implementation Rules**:
- Trend computed by comparing first half vs second half of the time window:
  ```python
  mid = start + (end - start) / 2
  first_mean  = df[df.timestamp <= mid]['rate_per_1000'].mean()
  second_mean = df[df.timestamp >  mid]['rate_per_1000'].mean()
  trend = "increasing" if second_mean > first_mean * 1.05 else \
          "decreasing" if second_mean < first_mean * 0.95 else "stable"
  ```
- Top codes: `df.groupby('code')['event_count'].sum().nlargest(3).to_dict()`
- Alerts: codes where latest `rate_per_1000` exceeds 2× their baseline from config
- Narrative template: `"Over the last {N}h, {panel} metrics on {platform} are {trend}. Top codes by volume: {codes}. {alert_count} threshold breaches detected."`

**Acceptance Criteria**:
- Returns trend = "increasing" when anomaly window data is in the range
- Returns trend = "stable" during baseline-only window
- Narrative contains actual metric values from tool results — no hardcoded example values

---

### Skill C10: Agent Memory — Short-Term and Long-Term

**Trigger**: User asks to build, fix, or extend agent memory.

**Behavior**:
- Short-term: load/save last 20 conversation turns per session from `agent_conversation` table
- Long-term: write/query anomaly observations from `agent_memory` table with 7-day retention

**Short-Term Rules**:
- `load_short_term(session_id)` → returns list of message dicts ordered by id ASC
- `save_short_term(session_id, history)` → insert new turns since last save (not the full history)
- Trim: after save, delete turns exceeding 20 per session:
  ```sql
  DELETE FROM agent_conversation
  WHERE session_id = ?
    AND id NOT IN (
      SELECT id FROM agent_conversation
      WHERE session_id = ?
      ORDER BY id DESC LIMIT 20
    )
  ```
- Trim applies only between turns — never mid-ReAct loop

**Long-Term Rules**:
- `write_memory(metric_type, code, platform, observation, severity)` — write with dedup check
- Dedup: skip if `(code, platform)` has an entry within 30 minutes of current time
- `query_memory(code=None, platform=None, days=7)` → returns matching entries within retention window
- `purge_old_memory()` → called on every write: `DELETE FROM agent_memory WHERE timestamp < datetime('now', '-7 days')`
- Long-term memory injected as system context prefix when user message matches `r"before|happened before|recurring|again"`

**Acceptance Criteria**:
- After 25 turns, `agent_conversation` for that session has exactly 20 rows
- `write_memory()` called twice within 30 min for same code+platform → second write is skipped
- `query_memory(code="ERR_2003")` after anomaly detection → returns at least one entry

---

### Skill C11: Agent Observability

**Trigger**: User asks to build or extend trace logging, the reasoning trace UI, or the ARIA health stats panel.

**Behavior**:
- Log every tool call step to `agent_trace` table
- Expose `get_trace(session_id, turn_id)` for UI rendering
- Expose `get_agent_health_stats()` for sidebar health panel
- Render trace in Streamlit as expandable section below each ARIA response

**Implementation Rules**:
- `log_trace(session_id, turn_id, step, tool_name, tool_input, tool_output, duration_ms, status)`:
  - Truncate `tool_output` to 2000 characters before storing
  - `status` must be one of: `"success"`, `"error"`, `"empty_result"`
- `get_agent_health_stats()` returns:
  ```python
  {
    "avg_steps_per_query":   float,  # AVG(max step per turn)
    "tool_call_frequency":   dict,   # {tool_name: count}
    "guardrail_g1_hits":     int,    # queries that hit max iterations
    "guardrail_g2_hits":     int,    # queries that hit time range cap
    "empty_result_rate":     float,  # % of tool calls returning empty
    "avg_response_latency_ms": float
  }
  ```
- Trace UI per step:
  ```python
  icon = "🟢" if status=="success" else "🔴" if status=="error" else "🟡"
  st.info(f"{icon} Step {step+1}: **{tool_name}** | "
          f"Input: {key_params} | Rows: {row_count} | {duration_ms}ms")
  ```
- Health stats rendered in `st.expander("🤖 ARIA Health")` in sidebar — never in main panel area
- Iteration badge: rendered inline in ARIA panel header after each response: `f"{len(trace)}/{config.AGENT_MAX_ITERATIONS} steps  ⏱ {total_ms}ms"`

**Acceptance Criteria**:
- After one ARIA query, `agent_trace` table has at least 1 row
- Reasoning trace expander shows correct step count matching actual tool calls made
- Health stats sidebar shows non-zero values after 3+ queries
- `tool_output` truncated at 2000 chars for long tool results

---

### Skill C12: ARIA Chat Panel UI

**Trigger**: User asks to build or fix the ARIA chat panel, suggestion chips, or trace display.

**Behavior**:
- Render full-width chat section below KPI Analyzer
- Show 6 suggestion chips on first load (before any message is sent)
- Render scrollable chat history with role-labeled messages
- Show reasoning trace expander below each assistant message
- Show iteration + latency badge in panel header after each response

**Implementation Rules**:
- Session ID: `st.session_state.setdefault("session_id", str(uuid.uuid4()))` — generated once per session
- `aria_started` flag: `False` until first message sent — controls chip visibility
- `aria_history`: list of `{"role": str, "content": str, "trace": list|None}` dicts
- Suggestion chips: `st.columns(3)` with 6 buttons — clicking a chip calls `handle_user_input(chip_text)`
- `handle_user_input(prompt)`:
  1. Append user message to `aria_history`
  2. Call `agent_core.run_agent(prompt, session_id)` → `(response, trace)`
  3. Append assistant message with trace to `aria_history`
  4. Set `aria_started = True`
  5. Call `st.rerun()`
- Never render the ARIA input while waiting for a response — show `st.spinner("ARIA is thinking...")` during agent call
- Chat history rendered using `st.chat_message(role)` blocks for visual distinction

**Acceptance Criteria**:
- Suggestion chips disappear after first message is sent
- Chat history persists across page rerenders within the same session
- Reasoning trace expander shows correct step count
- Spinner shows while agent is processing — does not leave blank state

---

## General Rules (Apply to All Skills)

1. **Session state**: all user-facing state lives in `st.session_state` — never global variables
2. **SQL safety**: all queries use `?` parameterized placeholders — never f-strings for SQL values
3. **Read-only agent**: no agent tool may execute INSERT/UPDATE/DELETE on the `metrics` table
4. **Error surfaces**: DB errors → log to console, return empty. Panel errors → `st.error()`. Tool errors → error envelope
5. **No hardcoding**: platform names, error codes, thresholds all come from `config.py`
6. **Batch inserts**: always `executemany()` for bulk data — never loop with `execute()`
7. **Timestamps**: always ISO 8601 strings in DB — always snapped to 5-min boundaries before storage
8. **Imports**: all imports at top of file — no inline imports inside functions
9. **Docstrings**: every public function must document its return type and note which parameters are SQL-injected vs safe
10. **Demo mode awareness**: every time-sensitive function checks `config.DEMO_MODE` for interval adjustments
