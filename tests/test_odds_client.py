from __future__ import annotations

import pytest
import requests_mock

from ev_finder.odds.client import OddsAPIClient, OddsAPIError
from ev_finder.odds.storage import store_snapshot


@pytest.fixture
def client() -> OddsAPIClient:
    return OddsAPIClient(api_key="test-key")


def test_fetch_odds_returns_events_and_redacts_api_key(client, sample_odds_event):
    with requests_mock.Mocker() as m:
        m.get(
            "https://api.the-odds-api.com/v4/sports/soccer_epl/odds",
            json=[sample_odds_event],
        )
        result = client.fetch_odds()

    assert result["events"] == [sample_odds_event]
    assert "apiKey" not in result["params"]
    assert result["params"]["regions"] == "uk,eu"


def test_fetch_odds_raises_on_401(client):
    with requests_mock.Mocker() as m:
        m.get("https://api.the-odds-api.com/v4/sports/soccer_epl/odds", status_code=401)
        with pytest.raises(OddsAPIError, match="invalid ODDS_API_KEY"):
            client.fetch_odds()


def test_fetch_odds_raises_on_429(client):
    with requests_mock.Mocker() as m:
        m.get("https://api.the-odds-api.com/v4/sports/soccer_epl/odds", status_code=429)
        with pytest.raises(OddsAPIError, match="quota exceeded"):
            client.fetch_odds()


def test_fetch_odds_raises_on_server_error(client):
    with requests_mock.Mocker() as m:
        m.get(
            "https://api.the-odds-api.com/v4/sports/soccer_epl/odds", status_code=500, text="boom"
        )
        with pytest.raises(OddsAPIError):
            client.fetch_odds()


def test_store_snapshot_persists_raw_and_flattened_rows(db_conn, sample_odds_event):
    fetch_result = {"params": {"regions": "uk,eu"}, "events": [sample_odds_event]}

    snapshot_id = store_snapshot(db_conn, sport_key="soccer_epl", fetch_result=fetch_result)

    snapshot_row = db_conn.execute(
        "SELECT * FROM raw_odds_snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    assert snapshot_row["sport_key"] == "soccer_epl"

    lines = db_conn.execute(
        "SELECT * FROM odds_lines WHERE snapshot_id = ? ORDER BY market, outcome_name",
        (snapshot_id,),
    ).fetchall()
    # 3 h2h outcomes + 2 totals outcomes for the one bookmaker in the fixture.
    assert len(lines) == 5
    assert {line["market"] for line in lines} == {"h2h", "totals"}
    assert all(line["home_team"] == "Arsenal" for line in lines)
