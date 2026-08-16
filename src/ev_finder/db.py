"""SQLite connection and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL,
    sport_key TEXT NOT NULL,
    params_json TEXT NOT NULL,
    response_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES raw_odds_snapshots(id),
    event_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    outcome_point REAL,
    price REAL NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_odds_lines_event ON odds_lines(event_id);
CREATE INDEX IF NOT EXISTS idx_odds_lines_snapshot ON odds_lines(snapshot_id);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
