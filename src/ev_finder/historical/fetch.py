"""Download historical EPL season CSVs from football-data.co.uk."""

from __future__ import annotations

import requests

BASE_URL = "https://www.football-data.co.uk/mmz4281"
REQUEST_TIMEOUT_SECONDS = 30


class HistoricalFetchError(RuntimeError):
    """Raised when a season CSV can't be downloaded."""


def season_code(start_year: int) -> str:
    """Convert a season's start year to football-data.co.uk's YYNN code.

    e.g. 2019 (the 2019/20 season) -> "1920".
    """
    end_year = start_year + 1
    return f"{start_year % 100:02d}{end_year % 100:02d}"


def download_season(start_year: int, session: requests.Session | None = None) -> str:
    """Download the raw E0.csv text for one EPL season.

    `start_year` is the season's start year, e.g. 2019 for the 2019/20 season.
    """
    session = session or requests.Session()
    url = f"{BASE_URL}/{season_code(start_year)}/E0.csv"
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise HistoricalFetchError(f"Request for season {start_year} failed: {exc}") from exc

    if not response.ok:
        raise HistoricalFetchError(
            f"Failed to download season {start_year} ({url}): HTTP {response.status_code}"
        )
    return response.text
