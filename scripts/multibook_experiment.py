"""Research script: does the model show edge against softer books, even
though it doesn't beat Bet365?

Reuses the same validated pure logic as the production backtest
(`ev_finder.backtest.engine._evaluate_market`, `DixonColesModel`) with only
the bookmaker columns swapped -- no changes to `run_backtest` or
`backtest_bets`, and nothing here is persisted to the database. This is
exploratory: it's meant to answer "is this worth building into the
pipeline" before spending time wiring it up properly.

Books compared, per football-data.co.uk's coverage in this dataset:
  - Bet365: 1X2 + totals (pre-closing and closing both available)
  - Pinnacle: 1X2 only (no totals odds were ever ingested for Pinnacle)
  - Market average: 1X2 + totals

Usage:
    uv run python scripts/multibook_experiment.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ev_finder.backtest.engine import DEFAULT_EDGE_THRESHOLD, _evaluate_market  # noqa: E402
from ev_finder.config import load_settings  # noqa: E402
from ev_finder.model.dixon_coles import DixonColesModel, UnknownTeamError  # noqa: E402

START = "2021-08-01"
END = "2024-05-31"

# book -> (h2h decision cols, h2h closing-ref cols, totals decision cols, totals closing-ref cols)
# totals cols are None where the book wasn't ingested for that market.
BOOKS = {
    "bet365": {
        "h2h_decision": ["b365_h", "b365_d", "b365_a"],
        "h2h_closing_ref": ["b365_close_h", "b365_close_d", "b365_close_a"],
        "totals_decision": ["b365_over_2_5", "b365_under_2_5"],
        "totals_closing_ref": ["b365_close_over_2_5", "b365_close_under_2_5"],
    },
    "pinnacle": {
        "h2h_decision": ["ps_h", "ps_d", "ps_a"],
        "h2h_closing_ref": ["ps_close_h", "ps_close_d", "ps_close_a"],
        "totals_decision": None,
        "totals_closing_ref": None,
    },
    "average": {
        "h2h_decision": ["avg_h", "avg_d", "avg_a"],
        "h2h_closing_ref": ["avg_close_h", "avg_close_d", "avg_close_a"],
        "totals_decision": ["avg_over_2_5", "avg_under_2_5"],
        "totals_closing_ref": ["avg_close_over_2_5", "avg_close_under_2_5"],
    },
}


def run_book_backtest(
    matches: pd.DataFrame, book_cols: dict, edge_threshold: float
) -> pd.DataFrame:
    """Walk-forward backtest for one book's odds columns. Returns a
    DataFrame of flagged bets (in-memory only, nothing persisted)."""
    start_ts, end_ts = pd.Timestamp(START), pd.Timestamp(END)
    in_range = matches.loc[(matches["date"] >= start_ts) & (matches["date"] <= end_ts)]
    dates = sorted(in_range["date"].unique())

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
                continue
            probs = model.market_probs(grid)

            rows: list[dict] = []
            if book_cols["h2h_decision"] is not None:
                rows += _evaluate_market(
                    probs,
                    ["home_win", "draw", "away_win"],
                    [row[c] for c in book_cols["h2h_decision"]],
                    [row[c] for c in book_cols["h2h_closing_ref"]],
                    {"H": "home_win", "D": "draw", "A": "away_win"}[row["ftr"]],
                    "h2h",
                    edge_threshold,
                    0.25,
                )
            if book_cols["totals_decision"] is not None:
                actual_totals = (
                    "over_2_5" if (row["home_goals"] + row["away_goals"]) >= 3 else "under_2_5"
                )
                rows += _evaluate_market(
                    probs,
                    ["over_2_5", "under_2_5"],
                    [row[c] for c in book_cols["totals_decision"]],
                    [row[c] for c in book_cols["totals_closing_ref"]],
                    actual_totals,
                    "totals",
                    edge_threshold,
                    0.25,
                )

            for r in rows:
                r["date"] = as_of_date
                r["home_team"] = home
                r["away_team"] = away
            all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def summarize_df(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_bets": 0,
            "roi": 0.0,
            "hit_rate": 0.0,
            "max_drawdown": 0.0,
            "avg_clv_pct": None,
            "pct_positive_clv": None,
        }
    staked = df["kelly_stake"].sum()
    pnl = df["pnl_units"].sum()
    roi = pnl / staked if staked else 0.0
    hit_rate = (df["outcome"] == df["actual_result"]).mean()

    cumulative = df.sort_values("date", kind="stable")["pnl_units"].cumsum()
    max_drawdown = (cumulative.cummax() - cumulative).max()

    clv = df["clv_pct"].dropna()
    avg_clv = float(clv.mean()) if len(clv) else None
    pct_positive_clv = float((clv > 0).mean()) if len(clv) else None
    return {
        "total_bets": len(df),
        "roi": roi,
        "hit_rate": hit_rate,
        "max_drawdown": max_drawdown,
        "avg_clv_pct": avg_clv,
        "pct_positive_clv": pct_positive_clv,
    }


def to_markdown_table(rows: list[dict]) -> str:
    headers = [
        "book",
        "market",
        "total_bets",
        "roi",
        "hit_rate",
        "max_drawdown",
        "avg_clv",
        "pct_positive_clv",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        if r["total_bets"] is None:
            cells = [r["book"], r["market"], "-", "-", "-", "-", "-", "-"]
        else:
            cells = [
                r["book"],
                r["market"],
                str(r["total_bets"]),
                f"{r['roi']:+.2%}",
                f"{r['hit_rate']:.1%}",
                f"{r['max_drawdown']:.2f}",
                f"{r['avg_clv_pct']:+.2f}%" if r["avg_clv_pct"] is not None else "n/a",
                f"{r['pct_positive_clv']:.1%}" if r["pct_positive_clv"] is not None else "n/a",
            ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_results_section(table_md: str) -> None:
    """Idempotently (re-)write the "## Multi-book comparison" section at
    the end of RESULTS.md, without touching anything generate_report.py
    owns above it."""
    results_path = REPO_ROOT / "RESULTS.md"
    content = results_path.read_text()
    marker = "## Multi-book comparison"
    if marker in content:
        content = content[: content.index(marker)].rstrip() + "\n"

    section = (
        f"\n{marker} (edge threshold > 3%)\n\n"
        "Same walk-forward methodology as the rest of this document (pre-closing decision, "
        "closing-only CLV), re-run against each book's own pre-closing/closing odds instead of "
        "always Bet365's. Pinnacle totals odds were never ingested (not available in the source "
        'data), hence "no data" there.\n\n'
        f"{table_md}\n"
    )
    results_path.write_text(content.rstrip("\n") + "\n" + section)


def main() -> None:
    settings = load_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row

    matches = pd.read_sql_query("SELECT * FROM historical_matches ORDER BY date, id", conn)
    matches["date"] = pd.to_datetime(matches["date"])
    conn.close()

    print(f"Multi-book comparison, {START} to {END}, edge threshold {DEFAULT_EDGE_THRESHOLD:.0%}\n")
    print(f"{'Book':<10} {'Market':<8} {'Bets':>6} {'ROI':>9} {'Hit rate':>10} {'Avg CLV':>10}")
    print("-" * 58)

    table_rows = []
    for book_name, book_cols in BOOKS.items():
        # One walk-forward pass per book covering whichever markets it has
        # data for -- the model fit doesn't depend on market, so splitting
        # this into separate h2h/totals passes would just refit twice for
        # no reason.
        book_df = run_book_backtest(matches, book_cols, DEFAULT_EDGE_THRESHOLD)

        for market in ("h2h", "totals"):
            if book_cols[f"{market}_decision"] is None:
                print(
                    f"{book_name:<10} {market:<8}      -         -          -          -  (no data)"
                )
                table_rows.append({"book": book_name, "market": market, "total_bets": None})
                continue
            market_df = book_df[book_df["market"] == market] if not book_df.empty else book_df
            summary = summarize_df(market_df)
            clv_str = (
                f"{summary['avg_clv_pct']:+.2f}%" if summary["avg_clv_pct"] is not None else "n/a"
            )
            print(
                f"{book_name:<10} {market:<8} {summary['total_bets']:>6} "
                f"{summary['roi']:>+8.2%} {summary['hit_rate']:>9.1%} {clv_str:>10}"
            )
            table_rows.append({"book": book_name, "market": market, **summary})

    write_results_section(to_markdown_table(table_rows))
    print("\nAppended/updated '## Multi-book comparison' section in RESULTS.md")


if __name__ == "__main__":
    main()
