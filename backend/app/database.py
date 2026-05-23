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
    """

    with get_connection() as connection:
        connection.executescript(schema)
        connection.commit()
