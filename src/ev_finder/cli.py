"""ev-finder CLI."""

from __future__ import annotations

import typer

from ev_finder.backtest.engine import (
    DEFAULT_EDGE_THRESHOLD,
    DEFAULT_KELLY_FRACTION,
    run_backtest,
)
from ev_finder.config import ConfigError, load_settings, require_odds_api_key
from ev_finder.db import get_connection, init_db
from ev_finder.historical.fetch import HistoricalFetchError, download_season
from ev_finder.historical.loader import load_dataframe, parse_csv
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


def _parse_seasons(seasons: str) -> list[int]:
    """Parse a "2019-2024" range into [2019, 2020, ..., 2024]."""
    try:
        start_str, end_str = seasons.split("-")
        start, end = int(start_str), int(end_str)
    except ValueError as exc:
        raise typer.BadParameter(
            f"--seasons must be START-END, e.g. 2019-2024 (got {seasons!r})"
        ) from exc
    if end < start:
        raise typer.BadParameter(f"--seasons end ({end}) must be >= start ({start})")
    return list(range(start, end + 1))


@app.command("ingest-historical")
def ingest_historical(
    seasons: str = typer.Option(
        "2019-2024", help="Season start-year range, e.g. 2019-2024 for 2019/20 through 2024/25."
    ),
) -> None:
    """Download EPL results + pre-closing/closing odds from football-data.co.uk and store them."""
    settings = load_settings()
    start_years = _parse_seasons(seasons)

    conn = get_connection(settings.db_path)
    init_db(conn)
    total_inserted = 0
    try:
        for start_year in start_years:
            label = f"{start_year}/{(start_year + 1) % 100:02d}"
            try:
                csv_text = download_season(start_year)
            except HistoricalFetchError as exc:
                typer.secho(f"Skipping season {label}: {exc}", fg=typer.colors.RED)
                continue

            df = parse_csv(csv_text)
            inserted = load_dataframe(conn, df)
            total_inserted += inserted
            typer.secho(
                f"Season {label}: {len(df)} matches parsed, {inserted} new row(s) inserted.",
                fg=typer.colors.GREEN,
            )
    finally:
        conn.close()

    typer.secho(f"Done. {total_inserted} new row(s) inserted in total.", fg=typer.colors.GREEN)


@app.command("backtest")
def backtest(
    start: str = typer.Option(..., help="Start date, inclusive (YYYY-MM-DD)."),
    end: str = typer.Option(..., help="End date, inclusive (YYYY-MM-DD)."),
    edge_threshold: float = typer.Option(
        DEFAULT_EDGE_THRESHOLD, help="Minimum model edge over vig-free market prob to flag a bet."
    ),
    kelly_fraction: float = typer.Option(
        DEFAULT_KELLY_FRACTION, help="Fraction of full Kelly to stake on flagged bets."
    ),
) -> None:
    """Walk-forward backtest the Dixon-Coles model against pre-closing odds,
    with true closing odds used only to score CLV on flagged bets."""
    settings = load_settings()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        summary = run_backtest(
            conn, start=start, end=end, edge_threshold=edge_threshold, kelly_fraction=kelly_fraction
        )
    finally:
        conn.close()

    typer.secho(f"Backtest {start} -> {end} (edge>{edge_threshold}, kelly x{kelly_fraction})")
    typer.echo(f"  Total bets:      {summary.total_bets}")
    typer.echo(f"  ROI:             {summary.roi:.2%}")
    typer.echo(f"  Hit rate:        {summary.hit_rate:.2%}")
    for market, roi in summary.roi_by_market.items():
        typer.echo(f"  ROI ({market}):{' ' * max(1, 6 - len(market))}{roi:.2%}")
    typer.echo(f"  Max drawdown:    {summary.max_drawdown:.2f} units")
    typer.echo(f"  Avg flagged edge:{summary.avg_edge:.2%}")
    if summary.avg_clv_pct is not None:
        typer.echo(f"  Avg CLV:         {summary.avg_clv_pct:+.2f}%")
        typer.echo(f"  % bets w/ +CLV:  {summary.pct_positive_clv:.1%}")


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
