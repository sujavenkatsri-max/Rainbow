"""
seed_data.py — Historical 24-hour seed for the ARIA STB KPI Analyzer.

Generates 288 timestamps × 4 platforms × 22 codes = 25,344 records on first launch.
Idempotent: checks seed_status before generating.
"""
from datetime import datetime, timedelta
from typing import List

import config
from ingest.metric_generator import generate_batch, snap_to_5min
from ingest.anomaly_injector import build_multiplier_map, apply_demo_anomalies
from storage.metrics_store import insert_metric_batch, is_seeded, mark_seeded
from ingest.schema import MetricRecord


def run_seed() -> None:
    """Seed 24 hours of historical metric data into SQLite.

    Idempotent — returns immediately if already seeded.
    Prints progress to console every 50 timestamps.
    Calls apply_demo_anomalies() after all data is inserted.
    """
    if is_seeded():
        print("[seed_data] Already seeded — skipping.")
        return

    seed_start = datetime.now() - timedelta(hours=config.HISTORICAL_SEED_HOURS)
    seed_end   = datetime.now() - timedelta(minutes=5)

    print(f"[seed_data] Seeding from {seed_start.isoformat()} to {seed_end.isoformat()}")

    # Build list of all 5-min timestamps in the seed window
    timestamps: List[datetime] = []
    current = snap_to_5min(seed_start)
    while current <= snap_to_5min(seed_end):
        timestamps.append(current)
        current += timedelta(minutes=5)

    total = len(timestamps)
    print(f"[seed_data] Generating {total} timestamps × 88 records = {total * 88} rows")

    batch_buffer: List[MetricRecord] = []
    BATCH_SIZE = 12  # 1 hour worth of timestamps

    try:
        for idx, ts in enumerate(timestamps):
            # No anomaly multipliers during initial seed pass —
            # anomalies applied via apply_demo_anomalies() after full insert
            records = generate_batch(ts, anomaly_multipliers={})
            batch_buffer.extend(records)

            if len(batch_buffer) >= BATCH_SIZE * 88:
                insert_metric_batch(batch_buffer)
                batch_buffer = []

            if (idx + 1) % 50 == 0:
                print(f"[seed_data] Progress: {idx + 1}/{total} timestamps processed")

        # Insert remaining buffer
        if batch_buffer:
            insert_metric_batch(batch_buffer)

        print(f"[seed_data] Base data inserted. Applying demo anomalies...")
        apply_demo_anomalies(seed_start)

        mark_seeded()
        print("[seed_data] Seed complete.")

    except Exception as exc:
        print(f"[seed_data] Seed failed — seed_status NOT marked: {exc}")
        raise
