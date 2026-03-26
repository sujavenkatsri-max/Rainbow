# config.py — Single source of truth for all ARIA constants and thresholds

# Platforms
PLATFORMS = ["Apollo", "EOS", "Horizon", "Liberty"]

# Ingestion
INGEST_INTERVAL_SECONDS       = 300         # 5 min real-time
DEMO_MODE                     = True        # True = 10-sec ticks
HISTORICAL_SEED_HOURS         = 24          # 288 data points on seed
ANOMALY_INJECTION_ENABLED     = True
ANOMALY_SCAN_INTERVAL_SECONDS = 120         # background scan every 2 min
DATA_RETENTION_HOURS          = 48

# Storage
SQLITE_DB_PATH = "stb_metrics.db"

# Agent
USE_MOCK_LLM                 = True         # False = real Anthropic SDK
ANTHROPIC_API_KEY            = ""           # set when USE_MOCK_LLM = False
AGENT_MODEL                  = "claude-sonnet-4-20250514"
AGENT_MAX_TOKENS             = 1000
AGENT_MAX_ITERATIONS         = 6
AGENT_MEMORY_MAX_TURNS       = 20
AGENT_MEMORY_RETENTION_DAYS  = 7
AGENT_MEMORY_DEDUP_MINUTES   = 30

# Thresholds
CRASH_STORM_MULTIPLIER    = 2.0
CPU_WARNING_THRESHOLD     = 80
CPU_CRITICAL_THRESHOLD    = 90
MEM_FREE_WARNING_MB       = 50
ANOMALY_ZSCORE_WARNING    = 2.0
ANOMALY_ZSCORE_CRITICAL   = 3.0

# UI
DEFAULT_TIME_RANGE_HOURS      = 24
AUTO_REFRESH_INTERVAL_SECONDS = 60

# Platform scale factors (multiplied onto stb_count)
PLATFORM_SCALE = {
    "Apollo":  1.0,
    "EOS":     0.75,
    "Horizon": 0.55,
    "Liberty": 0.40,
}

# Code registry — (baseline_rate_per_1000, stb_min, stb_max)
CODE_BASELINES = {
    "ERR_2001": (2.5,   800,  1200),
    "ERR_2002": (1.2,   400,   700),
    "ERR_2003": (3.1,   600,  1000),
    "ERR_2004": (0.8,   200,   500),
    "ERR_2005": (1.5,   300,   600),
    "ERR_2006": (4.2,  1000,  1800),
    "ERR_2007": (2.0,   500,   900),
    "ERR_2008": (0.6,   150,   400),
    "CRR_3001": (0.3,   100,   300),
    "CRR_3002": (1.8,   400,   800),
    "CRR_3003": (0.5,   150,   350),
    "CRR_3004": (1.1,   300,   600),
    "CRR_3005": (0.9,   250,   500),
    "CRR_3006": (0.4,    80,   200),
    "CRR_3007": (0.2,    50,   150),
    "CRR_3008": (0.1,    30,   100),
    # Resource metrics: (baseline_mean, baseline_std) — stb fields handled separately
    "CPU_AVG":          (55.0,   8.0),
    "CPU_P95":          (72.0,  10.0),
    "MEM_FREE_AVG":    (180.0,  25.0),
    "MEM_HEAP_USED":   (320.0,  30.0),
    "MEM_SWAP_USED":    (45.0,  12.0),
    "THERMAL_THROTTLE": (50.0,  15.0),
}

# Resource metric clamp bounds (min, max)
RESOURCE_BOUNDS = {
    "CPU_AVG":          (0.0,   100.0),
    "CPU_P95":          (0.0,   100.0),
    "MEM_FREE_AVG":    (0.0,   512.0),
    "MEM_HEAP_USED":   (0.0,   768.0),
    "MEM_SWAP_USED":   (0.0,   256.0),
    "THERMAL_THROTTLE":(0.0,  1000.0),
}

# Total active STBs per platform (used for resource event_count)
TOTAL_ACTIVE_STBS = {
    "Apollo":  10000,
    "EOS":      7500,
    "Horizon":  5500,
    "Liberty":  4000,
}

# Code → metric_type mapping
CODE_METRIC_TYPE = {}
for _code in ["ERR_2001","ERR_2002","ERR_2003","ERR_2004",
              "ERR_2005","ERR_2006","ERR_2007","ERR_2008"]:
    CODE_METRIC_TYPE[_code] = "error_rate"
for _code in ["CRR_3001","CRR_3002","CRR_3003","CRR_3004",
              "CRR_3005","CRR_3006","CRR_3007","CRR_3008"]:
    CODE_METRIC_TYPE[_code] = "crash_rate"
for _code in ["CPU_AVG","CPU_P95"]:
    CODE_METRIC_TYPE[_code] = "cpu_utilization"
for _code in ["MEM_FREE_AVG","MEM_HEAP_USED","MEM_SWAP_USED","THERMAL_THROTTLE"]:
    CODE_METRIC_TYPE[_code] = "memory_utilization"

# Codes grouped by metric type
CODES_BY_METRIC_TYPE = {
    "error_rate":         ["ERR_2001","ERR_2002","ERR_2003","ERR_2004",
                           "ERR_2005","ERR_2006","ERR_2007","ERR_2008"],
    "crash_rate":         ["CRR_3001","CRR_3002","CRR_3003","CRR_3004",
                           "CRR_3005","CRR_3006","CRR_3007","CRR_3008"],
    "cpu_utilization":    ["CPU_AVG","CPU_P95"],
    "memory_utilization": ["MEM_FREE_AVG","MEM_HEAP_USED","MEM_SWAP_USED","THERMAL_THROTTLE"],
}

# Human-readable descriptions
CODE_DESCRIPTIONS = {
    "ERR_2001": "Playback Failure — Stream Not Found",
    "ERR_2002": "Playback Failure — Codec Unsupported",
    "ERR_2003": "DRM License Acquisition Failure",
    "ERR_2004": "DRM Decryption Error",
    "ERR_2005": "Tuner Lock Failure",
    "ERR_2006": "Middleware Timeout",
    "ERR_2007": "EPG Data Parse Error",
    "ERR_2008": "App Crash on Launch",
    "CRR_3001": "Kernel Panic",
    "CRR_3002": "Out of Memory Kill (OOM)",
    "CRR_3003": "Watchdog Timeout",
    "CRR_3004": "Segmentation Fault — Player",
    "CRR_3005": "Segmentation Fault — Middleware",
    "CRR_3006": "Crash Loop Detected (3+ in 10 min)",
    "CRR_3007": "Firmware Assert Failure",
    "CRR_3008": "Boot Failure / Stuck in Recovery",
    "CPU_AVG":          "Average CPU Utilization (%)",
    "CPU_P95":          "P95 CPU Utilization (%)",
    "MEM_FREE_AVG":     "Average Free Memory (MB)",
    "MEM_HEAP_USED":    "Heap Memory Used (MB)",
    "MEM_SWAP_USED":    "Swap Memory Used (MB)",
    "THERMAL_THROTTLE": "Thermal Throttle Event Count",
}

# KPI classification for status
HIGHER_IS_WORSE = [
    "error_rate", "crash_rate", "cpu_utilization",
    "MEM_HEAP_USED", "MEM_SWAP_USED", "THERMAL_THROTTLE",
]
HIGHER_IS_BETTER = ["MEM_FREE_AVG"]

# Anomaly events for demo injection
ANOMALY_EVENTS = [
    {
        "label":      "DRM Outage — Apollo",
        "start_time": "T-4h",
        "end_time":   "T-2h",
        "platform":   "Apollo",
        "codes":      ["ERR_2003", "ERR_2004"],
        "multiplier": 4.5,
    },
    {
        "label":      "OOM Crash Wave — EOS",
        "start_time": "T-3h",
        "end_time":   "T-2.5h",
        "platform":   "EOS",
        "codes":      ["CRR_3002", "CRR_3006"],
        "multiplier": 3.0,
    },
    {
        "label":      "CPU Spike — Horizon",
        "start_time": "T-1.5h",
        "end_time":   "T-1h",
        "platform":   "Horizon",
        "codes":      ["CPU_AVG", "CPU_P95"],
        "multiplier": 1.6,
    },
]
