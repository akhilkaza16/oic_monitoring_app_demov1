from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DB_PATH = os.environ["SQLITE_DB_PATH"]
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS integrations (
      integration_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      project TEXT NOT NULL,
      business_domain TEXT NOT NULL,
      owner TEXT NOT NULL,
      endpoint_url TEXT NOT NULL,
      status TEXT NOT NULL,
      failed_instances INTEGER NOT NULL,
      connection_errors INTEGER NOT NULL,
      timeouts INTEGER NOT NULL,
      aborted_runs INTEGER NOT NULL,
      scheduled_runs_missed INTEGER NOT NULL,
      success_rate REAL NOT NULL,
      last_run_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS run_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      integration_id TEXT NOT NULL,
      event_time TEXT NOT NULL,
      run_status TEXT NOT NULL,
      duration_ms INTEGER NOT NULL,
      error_type TEXT,
      message TEXT NOT NULL,
      FOREIGN KEY (integration_id) REFERENCES integrations(integration_id)
    );

    CREATE TABLE IF NOT EXISTS latency_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      endpoint TEXT NOT NULL,
      method TEXT NOT NULL,
      latency_ms REAL NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      salt TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_login_security (
      email TEXT PRIMARY KEY,
      failed_count INTEGER NOT NULL DEFAULT 0,
      locked_until TEXT,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (email) REFERENCES admin_users(email)
    );

    CREATE TABLE IF NOT EXISTS admin_sessions (
      session_id TEXT PRIMARY KEY,
      email TEXT NOT NULL,
      issued_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      revoked_at TEXT,
      revoke_reason TEXT,
      FOREIGN KEY (email) REFERENCES admin_users(email)
    );

    CREATE TABLE IF NOT EXISTS password_reset_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      used_at TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY (email) REFERENCES admin_users(email)
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor_email TEXT,
      action_type TEXT NOT NULL,
      target TEXT NOT NULL,
      details TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS trend_snapshots (
      snapshot_date TEXT PRIMARY KEY,
      healthy_count INTEGER NOT NULL,
      warning_count INTEGER NOT NULL,
      critical_count INTEGER NOT NULL,
      unknown_count INTEGER NOT NULL,
      health_score REAL NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS alert_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      severity TEXT NOT NULL,
      integration_id TEXT NOT NULL,
      title TEXT NOT NULL,
      message TEXT NOT NULL,
      simulated_email_to TEXT NOT NULL,
      created_at TEXT NOT NULL,
      acknowledged INTEGER NOT NULL DEFAULT 0
    );
    """

    with get_connection() as connection:
        connection.executescript(schema)

        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(alert_events)").fetchall()
        }
        if "metric_type" not in existing_columns:
            connection.execute("ALTER TABLE alert_events ADD COLUMN metric_type TEXT")
        if "metric_value" not in existing_columns:
            connection.execute("ALTER TABLE alert_events ADD COLUMN metric_value INTEGER")

        connection.commit()
