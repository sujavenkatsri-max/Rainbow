"""
metric_generator.py — Core metric generation logic for all platforms × all codes.

Generates exactly 88 records per tick:
  4 platforms × (8 error + 8 crash + 6 resource) = 88
"""
import random
from datetime import datetime
from typing import List

import config
from ingest.schema import MetricRecord


def snap_to_5min(dt: datetime) -> datetime:
    """Floor datetime to nearest 5-minute boundary.

    Returns: datetime with second=0, microsecond=0, minute snapped down.
    """
    return dt.replace(second=0, microsecond=0, minute=(dt.minute // 5) * 5)


def time_of_day_factor(dt: datetime, base_rate: float) -> float:
    """Return an additive offset based on hour of day (diurnal pattern).

    Returns: float offset to add to base_rate.
    """
    hour = dt.hour
    if hour >= 20 or hour < 2:    # prime time 8PM–2AM: +25%
        return base_rate * 0.25
    elif 2 <= hour < 7:           # low traffic 2AM–7AM: -30%
        return base_rate * -0.30
    elif 7 <= hour < 10:          # morning ramp 7AM–10AM: +10%
        return base_rate * 0.10
    else:                          # daytime 10AM–8PM: baseline
        return 0.0


def generate_batch(timestamp: datetime, anomaly_multipliers: dict = None) -> List[MetricRecord]:
    """Generate one full tick of 88 MetricRecord objects.

    Parameters:
        timestamp: datetime — will be snapped to 5-min boundary internally.
        anomaly_multipliers: dict mapping (platform, code) → float multiplier.
            Safe (internal use only, not user-supplied).

    Returns: list of 88 MetricRecord objects.
    """
    if anomaly_multipliers is None:
        anomaly_multipliers = {}

    ts = snap_to_5min(timestamp)
    ts_str = ts.isoformat()
    records: List[MetricRecord] = []

    for platform in config.PLATFORMS:
        scale = config.PLATFORM_SCALE[platform]

        # ── Error + Crash codes ──────────────────────────────────────────
        for code in (config.CODES_BY_METRIC_TYPE["error_rate"] +
                     config.CODES_BY_METRIC_TYPE["crash_rate"]):
            base_rate, stb_min, stb_max = config.CODE_BASELINES[code]
            metric_type = config.CODE_METRIC_TYPE[code]

            stb_count = max(1, int(random.randint(int(stb_min), int(stb_max)) * scale))

            noise = random.gauss(0, base_rate * 0.15)
            tod_offset = time_of_day_factor(ts, base_rate)
            final_rate = max(0.0, base_rate + noise + tod_offset)

            multiplier = anomaly_multipliers.get((platform, code), 1.0)
            event_count = max(0, int((final_rate / 1000) * stb_count * multiplier))
            rate_per_1000 = (event_count / stb_count) * 1000

            records.append(MetricRecord(
                timestamp=ts_str,
                platform=platform,
                metric_type=metric_type,
                code=code,
                stb_count=stb_count,
                event_count=event_count,
                rate_per_1000=rate_per_1000,
            ))

        # ── Resource codes ───────────────────────────────────────────────
        total_stbs = max(1, int(config.TOTAL_ACTIVE_STBS[platform] * scale))

        for code in (config.CODES_BY_METRIC_TYPE["cpu_utilization"] +
                     config.CODES_BY_METRIC_TYPE["memory_utilization"]):
            mean_val, std_val = config.CODE_BASELINES[code]
            metric_type = config.CODE_METRIC_TYPE[code]

            low, high = config.RESOURCE_BOUNDS[code]
            value = random.gauss(mean_val, std_val)
            value = max(low, min(high, value))

            multiplier = anomaly_multipliers.get((platform, code), 1.0)
            value = min(high, value * multiplier)

            stb_count = total_stbs
            event_count = max(0, int(value * stb_count))
            # For resource metrics, rate_per_1000 IS the metric value
            rate_per_1000 = value

            records.append(MetricRecord(
                timestamp=ts_str,
                platform=platform,
                metric_type=metric_type,
                code=code,
                stb_count=stb_count,
                event_count=event_count,
                rate_per_1000=rate_per_1000,
            ))

    return records
