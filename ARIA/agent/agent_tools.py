"""
agent_tools.py — All 7 agent tool implementations. All tools read from SQLite only.

Every tool returns the standard envelope:
  {"status": "ok"|"empty"|"error", "data": [...], "meta": {...}}

meta always includes: tool_name, execution_time_ms, row_count, time_range.
All tools call log_trace() from agent_observability before returning.
"""
import time
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config
from storage.metrics_store import query_metrics as _query_metrics, get_latest_timestamp
from storage import agent_store
from dateutil.parser import parse as parse_dt
import re


# ── Internal helpers ─────────────────────────────────────────────────────────

def _make_meta(tool_name: str, start_ts: float, rows: Any, time_range: str) -> Dict:
    row_count = len(rows) if isinstance(rows, list) else (1 if rows else 0)
    return {
        "tool_name":        tool_name,
        "execution_time_ms": int((time.time() - start_ts) * 1000),
        "row_count":        row_count,
        "time_range":       time_range,
    }


def _envelope(status: str, data: Any, meta: Dict) -> Dict:
    return {"status": status, "data": data, "meta": meta}


def _classify_status(delta: float, pct_change: float, metric_type: str, code: str) -> str:
    """Classify a KPI change as Degraded / Improved / Stable."""
    if abs(pct_change) < 5:
        return "Stable"
    higher_is_worse = (
        metric_type in ["error_rate", "crash_rate", "cpu_utilization"]
        or code in ["MEM_HEAP_USED", "MEM_SWAP_USED", "THERMAL_THROTTLE"]
    )
    higher_is_better = code in ["MEM_FREE_AVG"]
    if higher_is_worse:
        return "Degraded" if delta > 0 else "Improved"
    if higher_is_better:
        return "Improved" if delta > 0 else "Degraded"
    return "Degraded" if delta > 0 else "Improved"


# ── Tool 1: query_metrics ────────────────────────────────────────────────────

def query_metrics(
    metric_type: str,
    platform: str,
    codes: List[str],
    start_time: str,
    end_time: str,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Query timeseries metrics from SQLite.

    Returns standard envelope. Rejects time ranges > 48h (Guardrail G2).
    All parameters are SQL-parameterized inside metrics_store.
    """
    t0 = time.time()
    tool_name = "query_metrics"
    time_range_str = f"{start_time} — {end_time}"

    try:
        duration_s = (parse_dt(end_time) - parse_dt(start_time)).total_seconds()
        if duration_s > 172800:
            meta = _make_meta(tool_name, t0, [], time_range_str)
            result = _envelope("error", None, {**meta, "reason": "time_range_exceeds_48h_limit"})
            agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                                  {"metric_type": metric_type, "platform": platform},
                                  result, int((time.time()-t0)*1000), "error")
            return result

        platforms = config.PLATFORMS if platform == "all" else [platform]
        rows = _query_metrics(metric_type, platforms, codes, start_time, end_time)

        status = "ok" if rows else "empty"
        meta = _make_meta(tool_name, t0, rows, time_range_str)
        result = _envelope(status, rows, meta)
    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], time_range_str)
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"metric_type": metric_type, "platform": platform,
                           "codes": codes},
                          result, int((time.time()-t0)*1000),
                          result["status"] if result["status"] != "ok" else "success")
    return result


# ── Tool 2: compare_kpi_windows ──────────────────────────────────────────────

def compare_kpi_windows(
    window_a_start: str,
    window_a_end: str,
    window_b_start: str,
    window_b_end: str,
    platform: str,
    metric_type: str = "all",
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Compare KPI metrics between two time windows.

    Returns delta records sorted by abs(pct_change) desc.
    float('inf') pct_change serialized as '+inf%'.
    """
    t0 = time.time()
    tool_name = "compare_kpi_windows"
    time_range_str = f"A:{window_a_start}–{window_a_end} B:{window_b_start}–{window_b_end}"

    try:
        platforms = config.PLATFORMS if platform == "all" else [platform]

        # Determine codes to compare
        if metric_type == "all":
            all_codes: List[str] = []
            for cl in config.CODES_BY_METRIC_TYPE.values():
                all_codes.extend(cl)
            mt_list = list(config.CODES_BY_METRIC_TYPE.keys())
        else:
            all_codes = config.CODES_BY_METRIC_TYPE.get(metric_type, [])
            mt_list = [metric_type]

        def _agg_window(start, end):
            rows = _query_metrics("all" if metric_type == "all" else metric_type,
                                  platforms, ["all"], start, end)
            agg: Dict[tuple, Dict] = {}
            for r in rows:
                key = (r["platform"], r["metric_type"], r["code"])
                if key not in agg:
                    agg[key] = {"stb_sum": 0, "event_sum": 0,
                                "rate_vals": [], "metric_type": r["metric_type"],
                                "code": r["code"], "platform": r["platform"]}
                agg[key]["stb_sum"]   += r["stb_count"]
                agg[key]["event_sum"] += r["event_count"]
                agg[key]["rate_vals"].append(r["rate_per_1000"])
            result = {}
            for key, v in agg.items():
                mean_rate = sum(v["rate_vals"]) / len(v["rate_vals"]) if v["rate_vals"] else 0.0
                result[key] = {
                    "platform":    v["platform"],
                    "metric_type": v["metric_type"],
                    "code":        v["code"],
                    "stb_count":   v["stb_sum"],
                    "event_count": v["event_sum"],
                    "rate_per_1000": mean_rate,
                }
            return result

        agg_a = _agg_window(window_a_start, window_a_end)
        agg_b = _agg_window(window_b_start, window_b_end)

        all_keys = set(agg_a.keys()) | set(agg_b.keys())
        deltas = []
        for key in all_keys:
            va = agg_a.get(key, {}).get("rate_per_1000", 0.0)
            vb = agg_b.get(key, {}).get("rate_per_1000", 0.0)
            ref = agg_a.get(key) or agg_b.get(key)
            delta = vb - va
            if va == 0 and vb == 0:
                pct = 0.0
                pct_str = "0%"
            elif va == 0:
                pct = float("inf")
                pct_str = "+inf%"
            else:
                pct = (delta / va) * 100
                pct_str = f"{pct:+.1f}%"

            status = _classify_status(delta, pct if pct != float("inf") else 999,
                                      ref["metric_type"], ref["code"])
            deltas.append({
                "platform":    ref["platform"],
                "metric_type": ref["metric_type"],
                "code":        ref["code"],
                "value_a":     round(va, 3),
                "value_b":     round(vb, 3),
                "delta":       round(delta, 3),
                "pct_change":  pct_str,
                "status":      status,
            })

        # Sort by abs magnitude (inf first)
        def _sort_key(d):
            p = d["pct_change"]
            if p == "+inf%":
                return float("inf")
            try:
                return abs(float(p.replace("%", "").replace("+", "")))
            except ValueError:
                return 0.0

        deltas.sort(key=_sort_key, reverse=True)

        status_str = "ok" if deltas else "empty"
        meta = _make_meta(tool_name, t0, deltas, time_range_str)
        result = _envelope(status_str, deltas, meta)
    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], time_range_str)
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"platform": platform, "metric_type": metric_type},
                          result, int((time.time()-t0)*1000),
                          "success" if result["status"] == "ok" else result["status"])
    return result


# ── Tool 3: detect_anomalies ─────────────────────────────────────────────────

def detect_anomalies(
    start_time: str,
    end_time: str,
    platform: str,
    threshold: float = None,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Detect z-score anomalies in the inspection window vs 24h baseline.

    Writes findings to long-term agent memory.
    All parameters are SQL-parameterized inside metrics_store.
    """
    if threshold is None:
        threshold = config.ANOMALY_ZSCORE_WARNING

    t0 = time.time()
    tool_name = "detect_anomalies"
    time_range_str = f"{start_time} — {end_time}"

    try:
        dt_start = parse_dt(start_time)
        dt_end   = parse_dt(end_time)
        baseline_start = (dt_start - timedelta(hours=24)).isoformat()

        platforms = config.PLATFORMS if platform == "all" else [platform]

        # Get baseline data
        baseline_rows = _query_metrics("all", platforms, ["all"],
                                       baseline_start, start_time)
        # Get inspection data
        inspect_rows = _query_metrics("all", platforms, ["all"],
                                      start_time, end_time)

        # Compute per (code, platform) baseline stats
        from collections import defaultdict
        import math

        baseline_vals: Dict[tuple, List[float]] = defaultdict(list)
        for r in baseline_rows:
            baseline_vals[(r["code"], r["platform"])].append(r["rate_per_1000"])

        baseline_stats: Dict[tuple, tuple] = {}
        for key, vals in baseline_vals.items():
            n = len(vals)
            if n < 2:
                continue
            mean = sum(vals) / n
            std  = math.sqrt(sum((v - mean) ** 2 for v in vals) / n)
            if std == 0:
                continue
            baseline_stats[key] = (mean, std)

        anomalies = []
        for r in inspect_rows:
            key = (r["code"], r["platform"])
            if key not in baseline_stats:
                continue
            mean, std = baseline_stats[key]
            z = (r["rate_per_1000"] - mean) / std
            if abs(z) >= threshold:
                severity = ("critical" if abs(z) >= config.ANOMALY_ZSCORE_CRITICAL
                            else "warning")
                anomalies.append({
                    "timestamp":     r["timestamp"],
                    "code":          r["code"],
                    "platform":      r["platform"],
                    "metric_type":   r["metric_type"],
                    "observed":      round(r["rate_per_1000"], 3),
                    "baseline_mean": round(mean, 3),
                    "z_score":       round(z, 2),
                    "severity":      severity,
                })
                agent_store.write_memory(
                    r["metric_type"], r["code"], r["platform"],
                    f"z-score={z:.1f}, observed={r['rate_per_1000']:.1f}, "
                    f"baseline={mean:.1f}",
                    severity,
                )

        status_str = "ok" if anomalies else "empty"
        meta = _make_meta(tool_name, t0, anomalies, time_range_str)
        result = _envelope(status_str, anomalies, meta)
    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], time_range_str)
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"start_time": start_time, "end_time": end_time,
                           "platform": platform},
                          result, int((time.time()-t0)*1000),
                          "success" if result["status"] == "ok" else result["status"])
    return result


# ── Tool 4: get_top_movers ───────────────────────────────────────────────────

def get_top_movers(
    window_a_start: str,
    window_a_end: str,
    window_b_start: str,
    window_b_end: str,
    platform: str,
    direction: str = "both",
    top_n: int = 5,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Get top KPI movers by magnitude of pct_change between two windows.

    Delegates to compare_kpi_windows internally.
    """
    t0 = time.time()
    tool_name = "get_top_movers"
    top_n = max(1, min(20, top_n))

    comparison = compare_kpi_windows(
        window_a_start, window_a_end, window_b_start, window_b_end,
        platform, "all", _session_id, _turn_id, _step,
    )

    if comparison["status"] == "error":
        agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                              {"direction": direction, "top_n": top_n},
                              comparison, int((time.time()-t0)*1000), "error")
        return comparison

    data = comparison.get("data") or []
    # Filter out Stable
    filtered = [d for d in data if d["status"] != "Stable"]

    if direction == "degraded":
        filtered = [d for d in filtered if d["status"] == "Degraded"]
    elif direction == "improved":
        filtered = [d for d in filtered if d["status"] == "Improved"]

    result_data = filtered[:top_n]
    status_str = "ok" if result_data else "empty"
    meta = _make_meta(tool_name, t0, result_data, f"top_{top_n}_{direction}")
    result = _envelope(status_str, result_data, meta)

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"direction": direction, "top_n": top_n},
                          result, int((time.time()-t0)*1000),
                          "success" if status_str == "ok" else status_str)
    return result


# ── Tool 5: get_current_snapshot ─────────────────────────────────────────────

def get_current_snapshot(
    platform: str,
    codes: List[str] = None,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Return the most recent 5-minute window values for a platform.

    Returns single-timestamp data — not a timeseries.
    """
    if codes is None:
        codes = ["all"]
    t0 = time.time()
    tool_name = "get_current_snapshot"

    try:
        latest_ts = get_latest_timestamp()
        platforms = config.PLATFORMS if platform == "all" else [platform]
        rows = _query_metrics("all", platforms, codes, latest_ts, latest_ts)
        status_str = "ok" if rows else "empty"
        meta = _make_meta(tool_name, t0, rows, latest_ts)
        result = _envelope(status_str, rows, meta)
    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], "")
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"platform": platform, "codes": codes},
                          result, int((time.time()-t0)*1000),
                          "success" if result["status"] == "ok" else result["status"])
    return result


# ── Tool 6: resolve_time_reference ───────────────────────────────────────────

def resolve_time_reference(
    time_reference: str,
    anchor: str = None,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Convert a natural language time reference to absolute ISO 8601 start/end.

    Results are snapped to 5-minute boundaries.
    Parameter time_reference is safe (user input, not SQL-injected).
    """
    from ingest.metric_generator import snap_to_5min

    t0 = time.time()
    tool_name = "resolve_time_reference"

    def _snap(dt):
        return snap_to_5min(dt).isoformat()

    try:
        now = parse_dt(anchor) if anchor else datetime.now()
        ref = time_reference.lower().strip()

        start = end = label = None
        ref_type = "point"

        # 12h clock: "3 pm", "11am", "3:30 PM"
        m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", ref)
        if m:
            h = int(m.group(1))
            mins = int(m.group(2)) if m.group(2) else 0
            ampm = m.group(3)
            if ampm == "pm" and h != 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0
            dt = now.replace(hour=h, minute=mins, second=0, microsecond=0)
            start = _snap(dt)
            end   = snap_to_5min(dt + timedelta(minutes=5)).isoformat()
            label = f"{h:02d}:{mins:02d}"
            ref_type = "point"

        # 24h clock: "14:00", "03:30"
        elif re.match(r"^(\d{1,2}):(\d{2})$", ref):
            m2 = re.match(r"^(\d{1,2}):(\d{2})$", ref)
            h, mins = int(m2.group(1)), int(m2.group(2))
            dt = now.replace(hour=h, minute=mins, second=0, microsecond=0)
            start = _snap(dt)
            end   = snap_to_5min(dt + timedelta(minutes=5)).isoformat()
            label = f"{h:02d}:{mins:02d}"
            ref_type = "point"

        # "N hours ago" / "Nh ago"
        elif re.search(r"(\d+)\s*h(?:ours?)?\s*ago", ref):
            m3 = re.search(r"(\d+)", ref)
            hours = int(m3.group(1))
            dt = now - timedelta(hours=hours)
            start = _snap(dt)
            end   = _snap(now)
            label = f"last {hours}h"
            ref_type = "range"

        # "N minutes ago"
        elif re.search(r"(\d+)\s*min(?:utes?)?\s*ago", ref):
            m4 = re.search(r"(\d+)", ref)
            mins = int(m4.group(1))
            dt = now - timedelta(minutes=mins)
            start = _snap(dt)
            end   = _snap(now)
            label = f"last {mins}min"
            ref_type = "range"

        elif "this morning" in ref:
            s = now.replace(hour=6,  minute=0, second=0, microsecond=0)
            e = now.replace(hour=12, minute=0, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(e), "this morning", "range"

        elif "this afternoon" in ref:
            s = now.replace(hour=12, minute=0, second=0, microsecond=0)
            e = now.replace(hour=17, minute=0, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(e), "this afternoon", "range"

        elif "this evening" in ref:
            s = now.replace(hour=17, minute=0, second=0, microsecond=0)
            e = now.replace(hour=21, minute=0, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(e), "this evening", "range"

        elif "last night" in ref:
            yesterday = now - timedelta(days=1)
            s = yesterday.replace(hour=20, minute=0, second=0, microsecond=0)
            e = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(e), "last night", "range"

        elif "yesterday" in ref:
            yesterday = now - timedelta(days=1)
            s = yesterday.replace(hour=0,  minute=0, second=0, microsecond=0)
            e = yesterday.replace(hour=23, minute=59, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(e), "yesterday", "range"

        elif "today" in ref:
            s = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start, end, label, ref_type = _snap(s), _snap(now), "today", "range"

        else:
            meta = _make_meta(tool_name, t0, [], "")
            result = _envelope("error", None,
                               {**meta, "reason": "unrecognized_time_reference"})
            agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                                  {"time_reference": time_reference},
                                  result, int((time.time()-t0)*1000), "error")
            return result

        data = {"start": start, "end": end, "label": label, "type": ref_type}
        meta = _make_meta(tool_name, t0, [data], f"{start}–{end}")
        result = _envelope("ok", data, meta)

    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], "")
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"time_reference": time_reference},
                          result, int((time.time()-t0)*1000),
                          "success" if result["status"] == "ok" else result["status"])
    return result


# ── Tool 7: summarize_panel ──────────────────────────────────────────────────

def summarize_panel(
    panel: str,
    platform: str,
    time_range_hours: int = 6,
    _session_id: str = "",
    _turn_id: int = 0,
    _step: int = 0,
) -> Dict:
    """Generate a structured panel summary with trend, top codes, alerts, narrative.

    All parameters are safe (internal use / enum values, not SQL-injected).
    """
    t0 = time.time()
    tool_name = "summarize_panel"

    PANEL_METRIC_MAP = {
        "error_rate":  "error_rate",
        "crash_rate":  "crash_rate",
        "resource":    "all",
    }

    try:
        end   = datetime.now()
        start = end - timedelta(hours=time_range_hours)
        metric_type_q = PANEL_METRIC_MAP.get(panel, "error_rate")
        platforms = config.PLATFORMS if platform == "all" else [platform]

        rows = _query_metrics(metric_type_q, platforms, ["all"],
                              start.isoformat(), end.isoformat())

        if not rows:
            meta = _make_meta(tool_name, t0, [], f"{start.isoformat()}–{end.isoformat()}")
            result = _envelope("empty", None, meta)
            agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                                  {"panel": panel, "platform": platform},
                                  result, int((time.time()-t0)*1000), "empty_result")
            return result

        # Trend: compare first half vs second half of window
        mid = start + (end - start) / 2
        mid_str = mid.isoformat()
        first_vals  = [r["rate_per_1000"] for r in rows if r["timestamp"] <= mid_str]
        second_vals = [r["rate_per_1000"] for r in rows if r["timestamp"] >  mid_str]

        first_mean  = sum(first_vals)  / len(first_vals)  if first_vals  else 0.0
        second_mean = sum(second_vals) / len(second_vals) if second_vals else 0.0

        if second_mean > first_mean * 1.05:
            trend = "increasing"
        elif second_mean < first_mean * 0.95:
            trend = "decreasing"
        else:
            trend = "stable"

        # Top codes by event_count sum
        code_event: Dict[str, int] = {}
        for r in rows:
            code_event[r["code"]] = code_event.get(r["code"], 0) + r["event_count"]
        top_codes = dict(sorted(code_event.items(), key=lambda x: x[1], reverse=True)[:3])

        # Alerts: latest rate > 2× baseline
        latest_ts = max(r["timestamp"] for r in rows)
        latest_rows = [r for r in rows if r["timestamp"] == latest_ts]
        alerts = []
        for r in latest_rows:
            if r["code"] in config.CODE_BASELINES:
                baseline_rate = config.CODE_BASELINES[r["code"]][0]
                if r["rate_per_1000"] > baseline_rate * 2:
                    alerts.append(r["code"])

        narrative = (
            f"Over the last {time_range_hours}h, {panel} metrics on {platform} are "
            f"{trend}. Top codes by volume: "
            + ", ".join(f"{c}={v}" for c, v in top_codes.items())
            + f". {len(alerts)} threshold breach(es) detected."
        )

        data = {
            "trend":     trend,
            "top_codes": top_codes,
            "alerts":    alerts,
            "narrative": narrative,
            "first_half_mean":  round(first_mean, 3),
            "second_half_mean": round(second_mean, 3),
        }
        meta = _make_meta(tool_name, t0, rows, f"{start.isoformat()}–{end.isoformat()}")
        result = _envelope("ok", data, meta)

    except Exception as exc:
        meta = _make_meta(tool_name, t0, [], "")
        result = _envelope("error", None, {**meta, "reason": str(exc)})

    agent_store.log_trace(_session_id, _turn_id, _step, tool_name,
                          {"panel": panel, "platform": platform,
                           "time_range_hours": time_range_hours},
                          result, int((time.time()-t0)*1000),
                          "success" if result["status"] == "ok" else result["status"])
    return result


# ── Tool dispatch registry ───────────────────────────────────────────────────

TOOL_REGISTRY = {
    "query_metrics":        query_metrics,
    "compare_kpi_windows":  compare_kpi_windows,
    "detect_anomalies":     detect_anomalies,
    "get_top_movers":       get_top_movers,
    "get_current_snapshot": get_current_snapshot,
    "resolve_time_reference": resolve_time_reference,
    "summarize_panel":      summarize_panel,
}
