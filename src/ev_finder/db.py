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

CREATE TABLE IF NOT EXISTS historical_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    ftr TEXT NOT NULL,
    b365_h REAL,
    b365_d REAL,
    b365_a REAL,
    ps_h REAL,
    ps_d REAL,
    ps_a REAL,
    avg_h REAL,
    avg_d REAL,
    avg_a REAL,
    b365_over_2_5 REAL,
    b365_under_2_5 REAL,
    avg_over_2_5 REAL,
    avg_under_2_5 REAL,
    UNIQUE(date, home_team, away_team)
);

CREATE INDEX IF NOT EXISTS idx_historical_matches_date ON historical_matches(date);

CREATE TABLE IF NOT EXISTS backtest_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    market TEXT NOT NULL,
    outcome TEXT NOT NULL,
    model_prob REAL NOT NULL,
    market_prob_no_vig REAL NOT NULL,
    edge REAL NOT NULL,
    kelly_stake REAL NOT NULL,
    actual_result TEXT,
    pnl_units REAL
);

CREATE INDEX IF NOT EXISTS idx_backtest_bets_date ON backtest_bets(date);
CREATE INDEX IF NOT EXISTS idx_backtest_bets_market ON backtest_bets(market);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
