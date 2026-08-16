"""Client for The Odds API (https://the-odds-api.com/)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import requests

BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_SPORT = "soccer_epl"
DEFAULT_REGIONS = "uk,eu"
DEFAULT_MARKETS = "h2h,totals"
REQUEST_TIMEOUT_SECONDS = 15


class OddsAPIError(RuntimeError):
    """Raised for non-transient failures talking to The Odds API."""


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class OddsAPIClient:
    """Thin wrapper around The Odds API's /odds endpoint."""

    def __init__(
        self, api_key: str, base_url: str = BASE_URL, session: requests.Session | None = None
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.session = session or requests.Session()

    def fetch_odds(
        self,
        sport: str = DEFAULT_SPORT,
        days_ahead: int = 7,
        regions: str = DEFAULT_REGIONS,
        markets: str = DEFAULT_MARKETS,
    ) -> dict[str, Any]:
        """Fetch odds for `sport` over the next `days_ahead` days.

        Returns a dict with the parsed JSON response plus the request params
        actually used, so callers can persist both.
        """
        now = datetime.now(UTC)
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "commenceTimeFrom": _iso(now),
            "commenceTimeTo": _iso(now + timedelta(days=days_ahead)),
        }
        url = f"{self.base_url}/sports/{sport}/odds"

        try:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise OddsAPIError(f"Request to The Odds API failed: {exc}") from exc

        if response.status_code == 401:
            raise OddsAPIError("The Odds API rejected the request: invalid ODDS_API_KEY (401).")
        if response.status_code == 429:
            raise OddsAPIError(
                "The Odds API quota exceeded (429) -- free tier is 500 requests/month."
            )
        if not response.ok:
            raise OddsAPIError(
                f"The Odds API returned an unexpected error: "
                f"{response.status_code} {response.text[:200]}"
            )

        # Redact the API key before it's persisted anywhere.
        safe_params = {k: v for k, v in params.items() if k != "apiKey"}
        return {"params": safe_params, "events": response.json()}
