"""Walk-forward backtest: refit Dixon-Coles per matchday, flag +EV bets
against Bet365 closing odds, and log them to `backtest_bets`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd

from ev_finder.ev.vig import remove_vig
from ev_finder.model.dixon_coles import DixonColesModel, UnknownTeamError

DEFAULT_EDGE_THRESHOLD = 0.03
DEFAULT_KELLY_FRACTION = 0.25


def fractional_kelly_stake(
    model_prob: float, decimal_odds: float, kelly_fraction: float = DEFAULT_KELLY_FRACTION
) -> float:
    """Fractional Kelly stake, as a fraction of bankroll, for a single bet.

    Uses net odds b = decimal_odds - 1 and full Kelly f* = (b*p - (1-p)) / b.
    Returns 0.0 whenever f* would be non-positive (model_prob * decimal_odds
    <= 1, i.e. no edge).
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    full_kelly = (b * model_prob - (1.0 - model_prob)) / b
    return max(0.0, full_kelly) * kelly_fraction


@dataclass
class BacktestSummary:
    total_bets: int
    roi: float
    hit_rate: float
    roi_by_market: dict[str, float]
    max_drawdown: float
    avg_edge: float


def _actual_result_h2h(ftr: str) -> str:
    return {"H": "home_win", "D": "draw", "A": "away_win"}[ftr]


def _actual_result_totals(home_goals: int, away_goals: int) -> str:
    return "over_2_5" if (home_goals + away_goals) >= 3 else "under_2_5"


def _evaluate_market(
    model_probs: dict[str, float],
    outcomes: list[str],
    odds: list,
    actual_result: str,
    market: str,
    edge_threshold: float,
    kelly_fraction: float,
) -> list[dict]:
    """Compare model probs to vig-free market probs for one market; return
    a row per outcome whose edge exceeds `edge_threshold`."""
    # pandas.read_sql_query turns SQL NULLs into NaN for float columns (not
    # None), so both need checking -- and SQLite itself treats a bound NaN
    # as NULL for NOT NULL columns, so a stray NaN here would otherwise
    # surface later as a confusing IntegrityError on insert.
    if any(o is None or pd.isna(o) for o in odds):
        return []  # odds missing for this market on this match -- skip it

    fair_probs = remove_vig(list(odds))
    flagged = []
    for outcome, market_prob, price in zip(outcomes, fair_probs, odds, strict=True):
        model_prob = model_probs[outcome]
        edge = model_prob - market_prob
        if edge <= edge_threshold:
            continue
        stake = fractional_kelly_stake(model_prob, price, kelly_fraction)
        won = outcome == actual_result
        pnl = stake * (price - 1.0) if won else -stake
        flagged.append(
            {
                "market": market,
                "outcome": outcome,
                "model_prob": model_prob,
                "market_prob_no_vig": market_prob,
                "edge": edge,
                "kelly_stake": stake,
                "actual_result": actual_result,
                "pnl_units": pnl,
            }
        )
    return flagged


def run_backtest(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> BacktestSummary:
    """Walk-forward backtest over [start, end] (inclusive dates).

    Refits the model once per unique fixture date on all matches strictly
    before that date (see DixonColesModel.fit's as_of_date semantics --
    this is what keeps the backtest leak-free), predicts every match on
    that date, flags +EV bets against Bet365 closing odds, and (re)writes
    them to `backtest_bets`. Re-running with the same [start, end] replaces
    that range's rows rather than accumulating duplicates.
    """
    matches = pd.read_sql_query("SELECT * FROM historical_matches ORDER BY date", conn)
    matches["date"] = pd.to_datetime(matches["date"])
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    in_range = matches.loc[(matches["date"] >= start_ts) & (matches["date"] <= end_ts)]
    dates = sorted(in_range["date"].unique())

    conn.execute("DELETE FROM backtest_bets WHERE date >= ? AND date <= ?", (start, end))
    conn.commit()

    prev_model: DixonColesModel | None = None
    all_rows: list[dict] = []

    for as_of_date in dates:
        model = DixonColesModel()
        model.fit(matches, as_of_date=as_of_date, warm_start=prev_model)
        prev_model = model

        day_matches = matches.loc[matches["date"] == as_of_date]
        for _, row in day_matches.iterrows():
            home, away = row["home_team"], row["away_team"]
            try:
                grid = model.predict(home, away)
            except UnknownTeamError:
                continue  # team's season debut -- no prior data to have predicted it
            probs = model.market_probs(grid)

            rows = _evaluate_market(
                probs,
                ["home_win", "draw", "away_win"],
                [row["b365_h"], row["b365_d"], row["b365_a"]],
                _actual_result_h2h(row["ftr"]),
                "h2h",
                edge_threshold,
                kelly_fraction,
            )
            rows += _evaluate_market(
                probs,
                ["over_2_5", "under_2_5"],
                [row["b365_over_2_5"], row["b365_under_2_5"]],
                _actual_result_totals(row["home_goals"], row["away_goals"]),
                "totals",
                edge_threshold,
                kelly_fraction,
            )

            for r in rows:
                r["date"] = as_of_date.strftime("%Y-%m-%d")
                r["home_team"] = home
                r["away_team"] = away
            all_rows.extend(rows)

    if all_rows:
        conn.executemany(
            """
            INSERT INTO backtest_bets
                (date, home_team, away_team, market, outcome, model_prob,
                 market_prob_no_vig, edge, kelly_stake, actual_result, pnl_units)
            VALUES (:date, :home_team, :away_team, :market, :outcome, :model_prob,
                    :market_prob_no_vig, :edge, :kelly_stake, :actual_result, :pnl_units)
            """,
            all_rows,
        )
        conn.commit()

    return summarize(conn, start, end)


def summarize(conn: sqlite3.Connection, start: str, end: str) -> BacktestSummary:
    df = pd.read_sql_query(
        "SELECT * FROM backtest_bets WHERE date >= ? AND date <= ? ORDER BY date",
        conn,
        params=(start, end),
    )
    if df.empty:
        return BacktestSummary(
            total_bets=0, roi=0.0, hit_rate=0.0, roi_by_market={}, max_drawdown=0.0, avg_edge=0.0
        )

    total_staked = df["kelly_stake"].sum()
    total_pnl = df["pnl_units"].sum()
    roi = total_pnl / total_staked if total_staked else 0.0
    hit_rate = (df["outcome"] == df["actual_result"]).mean()

    roi_by_market = {}
    for market, group in df.groupby("market"):
        staked = group["kelly_stake"].sum()
        roi_by_market[market] = group["pnl_units"].sum() / staked if staked else 0.0

    cumulative = df["pnl_units"].cumsum()
    max_drawdown = (cumulative.cummax() - cumulative).max()

    return BacktestSummary(
        total_bets=len(df),
        roi=roi,
        hit_rate=hit_rate,
        roi_by_market=roi_by_market,
        max_drawdown=max_drawdown,
        avg_edge=df["edge"].mean(),
    )
