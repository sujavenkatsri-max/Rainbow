"""
db_init.py — SQLite schema initialization for ARIA STB KPI Analyzer.
Exposes init_db() (idempotent) and reset_db() (full drop-recreate for demos).
"""
import sqlite3
import config


def init_db() -> None:
    """Create all tables and indexes if they do not already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS throughout.
    No SQL injection risk; no user-supplied parameters.
    """
    with sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False) as conn:
        conn.executescript("""
            -- ── METRICS TABLE ──────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS metrics (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                platform      TEXT    NOT NULL,
                metric_type   TEXT    NOT NULL,
                code          TEXT    NOT NULL,
                stb_count     INTEGER NOT NULL,
                event_count   INTEGER NOT NULL,
                rate_per_1000 REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_main
                ON metrics (timestamp, platform, metric_type, code);
            CREATE INDEX IF NOT EXISTS idx_metrics_time
                ON metrics (timestamp);

            -- ── SEED STATUS ────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS seed_status (
                id        INTEGER PRIMARY KEY,
                seeded    INTEGER NOT NULL DEFAULT 0,
                seeded_at TEXT
            );

            -- ── AGENT CONVERSATION (short-term memory) ─────────────────────
            CREATE TABLE IF NOT EXISTS agent_conversation (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                timestamp  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON agent_conversation (session_id, id);

            -- ── AGENT MEMORY (long-term anomaly observations) ──────────────
            CREATE TABLE IF NOT EXISTS agent_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                code        TEXT NOT NULL,
                platform    TEXT NOT NULL,
                observation TEXT NOT NULL,
                severity    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_code
                ON agent_memory (code, platform, timestamp);

            -- ── AGENT TRACE (observability) ────────────────────────────────
            CREATE TABLE IF NOT EXISTS agent_trace (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                turn_id     INTEGER NOT NULL,
                step        INTEGER NOT NULL,
                tool_name   TEXT,
                tool_input  TEXT,
                tool_output TEXT,
                duration_ms INTEGER,
                status      TEXT,
                timestamp   TEXT    NOT NULL
            );
        """)
        conn.commit()


def reset_db() -> None:
    """Drop and recreate all tables (demo reset).

    Drops in reverse dependency order to avoid FK constraint issues.
    No SQL injection risk; no user-supplied parameters.
    """
    with sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False) as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS agent_trace;
            DROP TABLE IF EXISTS agent_memory;
            DROP TABLE IF EXISTS agent_conversation;
            DROP TABLE IF EXISTS seed_status;
            DROP TABLE IF EXISTS metrics;
        """)
        conn.commit()
    init_db()
