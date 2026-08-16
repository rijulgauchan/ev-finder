from __future__ import annotations

from pathlib import Path

import pytest

from ev_finder.db import get_connection, init_db


@pytest.fixture
def db_conn(tmp_path: Path):
    conn = get_connection(tmp_path / "test_odds.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_odds_event() -> dict:
    """A single EPL event as returned by The Odds API's /odds endpoint."""
    return {
        "id": "evt_123",
        "sport_key": "soccer_epl",
        "commence_time": "2026-08-20T14:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmakers": [
            {
                "key": "bet365",
                "title": "Bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.10},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Chelsea", "price": 3.60},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.90},
                            {"name": "Under", "point": 2.5, "price": 1.95},
                        ],
                    },
                ],
            }
        ],
    }
