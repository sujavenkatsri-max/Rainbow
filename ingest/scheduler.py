"""
scheduler.py — APScheduler wiring for background metric ingestion and anomaly scanning.

Uses BackgroundScheduler in daemon mode. All jobs have misfire_grace_time=60 and coalesce=True.
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import config
from ingest.metric_generator import generate_batch, snap_to_5min
from storage.metrics_store import insert_metric_batch, purge_old_metrics


def generate_and_store_live_batch() -> None:
    """Generate one tick of 88 records at the current 5-min boundary and insert.

    Called by the metric_ingest scheduler job.
    """
    try:
        ts = snap_to_5min(datetime.now())
        records = generate_batch(ts)
        insert_metric_batch(records)
    except Exception as exc:
        print(f"[scheduler] generate_and_store_live_batch error: {exc}")


def run_background_anomaly_scan() -> None:
    """Run detect_anomalies for the last 30 minutes on all platforms and write to memory.

    Called by the anomaly_scan scheduler job.
    """
    try:
        # Import here to avoid circular imports at module load time
        from agent.agent_tools import detect_anomalies
        end_time   = datetime.now().isoformat()
        start_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        for platform in config.PLATFORMS:
            detect_anomalies(
                start_time=start_time,
                end_time=end_time,
                platform=platform,
                threshold=config.ANOMALY_ZSCORE_WARNING,
            )
    except Exception as exc:
        print(f"[scheduler] run_background_anomaly_scan error: {exc}")


def _purge_job() -> None:
    """Wrapper to call purge_old_metrics with the configured retention hours."""
    try:
        deleted = purge_old_metrics(config.DATA_RETENTION_HOURS)
        if deleted:
            print(f"[scheduler] Purged {deleted} old metric rows.")
    except Exception as exc:
        print(f"[scheduler] purge_job error: {exc}")


def start_background_engine() -> BackgroundScheduler:
    """Start all background scheduler jobs and return the running scheduler.

    Returns: BackgroundScheduler instance (daemon=True).
    """
    scheduler = BackgroundScheduler(daemon=True)

    interval_seconds = 10 if config.DEMO_MODE else config.INGEST_INTERVAL_SECONDS

    scheduler.add_job(
        func=generate_and_store_live_batch,
        trigger="interval",
        seconds=interval_seconds,
        id="metric_ingest",
        misfire_grace_time=60,
        coalesce=True,
    )

    scheduler.add_job(
        func=run_background_anomaly_scan,
        trigger="interval",
        seconds=config.ANOMALY_SCAN_INTERVAL_SECONDS,
        id="anomaly_scan",
        misfire_grace_time=60,
        coalesce=True,
    )

    scheduler.add_job(
        func=_purge_job,
        trigger="interval",
        hours=1,
        id="data_retention",
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.start()
    print(f"[scheduler] Background engine started (tick={interval_seconds}s).")
    return scheduler
