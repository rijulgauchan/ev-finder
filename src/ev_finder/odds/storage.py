"""Persist raw and normalized odds data into SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def store_snapshot(conn: sqlite3.Connection, sport_key: str, fetch_result: dict[str, Any]) -> int:
    """Store a raw API response and its normalized odds lines.

    Returns the new snapshot id.
    """
    fetched_at = _now_iso()
    events = fetch_result["events"]
    params = fetch_result["params"]

    cursor = conn.execute(
        "INSERT INTO raw_odds_snapshots (fetched_at, sport_key, params_json, response_json) "
        "VALUES (?, ?, ?, ?)",
        (fetched_at, sport_key, json.dumps(params), json.dumps(events)),
    )
    snapshot_id = cursor.lastrowid

    rows = list(_flatten_events(snapshot_id, events, fetched_at))
    conn.executemany(
        "INSERT INTO odds_lines "
        "(snapshot_id, event_id, home_team, away_team, commence_time, bookmaker, "
        " market, outcome_name, outcome_point, price, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return snapshot_id


def _flatten_events(snapshot_id: int, events: list[dict[str, Any]], fetched_at: str):
    for event in events:
        event_id = event.get("id", "")
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        commence_time = event.get("commence_time", "")
        for bookmaker in event.get("bookmakers", []):
            bookmaker_key = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    yield (
                        snapshot_id,
                        event_id,
                        home_team,
                        away_team,
                        commence_time,
                        bookmaker_key,
                        market_key,
                        outcome.get("name", ""),
                        outcome.get("point"),
                        outcome.get("price"),
                        fetched_at,
                    )
