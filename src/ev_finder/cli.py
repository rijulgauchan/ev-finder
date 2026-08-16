"""ev-finder CLI."""

from __future__ import annotations

import typer

from ev_finder.config import ConfigError, load_settings, require_odds_api_key
from ev_finder.db import get_connection, init_db
from ev_finder.odds.client import DEFAULT_SPORT, OddsAPIClient, OddsAPIError
from ev_finder.odds.storage import store_snapshot

app = typer.Typer(help="Find positive expected value bets on football (soccer) match markets.")


def _not_implemented(command: str) -> None:
    typer.secho(
        f"'{command}' is not implemented yet -- coming in the model phase.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=1)


@app.command("fetch-odds")
def fetch_odds(
    sport: str = typer.Option(DEFAULT_SPORT, help="The Odds API sport key."),
    days: int = typer.Option(7, help="How many days ahead to fetch odds for."),
) -> None:
    """Fetch upcoming odds and store them in SQLite."""
    settings = load_settings()
    try:
        api_key = require_odds_api_key(settings)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    client = OddsAPIClient(api_key=api_key)
    try:
        result = client.fetch_odds(sport=sport, days_ahead=days)
    except OddsAPIError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        snapshot_id = store_snapshot(conn, sport_key=sport, fetch_result=result)
    finally:
        conn.close()

    num_events = len(result["events"])
    typer.secho(
        f"Fetched {num_events} event(s) for '{sport}' -> snapshot #{snapshot_id} "
        f"({settings.db_path})",
        fg=typer.colors.GREEN,
    )


@app.command("update-ratings")
def update_ratings() -> None:
    """Recompute team attack/defense ratings from recent results. (Not implemented yet.)"""
    _not_implemented("update-ratings")


@app.command("find-value")
def find_value() -> None:
    """Flag bets where the model's edge over the market exceeds the threshold.

    Not implemented yet.
    """
    _not_implemented("find-value")


@app.command("log-bet")
def log_bet() -> None:
    """Log a flagged bet for tracking. (Not implemented yet.)"""
    _not_implemented("log-bet")


@app.command("report")
def report() -> None:
    """Report CLV/ROI over tracked bets. (Not implemented yet.)"""
    _not_implemented("report")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
