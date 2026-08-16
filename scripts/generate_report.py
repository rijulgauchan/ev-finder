"""Generate RESULTS.md and the README charts from a fresh backtest run.

Reproduces the numbers quoted in README.md and RESULTS.md: runs the
walk-forward backtest at the default edge threshold plus a threshold
sweep, and writes:

    assets/cumulative_pnl.png
    assets/roi_by_threshold.png
    RESULTS.md

Usage:
    uv run python scripts/generate_report.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ev_finder.backtest.engine import DEFAULT_KELLY_FRACTION, run_backtest  # noqa: E402
from ev_finder.config import load_settings  # noqa: E402
from ev_finder.db import init_db  # noqa: E402

START = "2021-08-01"
END = "2024-05-31"
DEFAULT_EDGE = 0.03
THRESHOLD_SWEEP = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10]

ASSETS_DIR = REPO_ROOT / "assets"
RESULTS_PATH = REPO_ROOT / "RESULTS.md"

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#444444",
        "axes.labelcolor": "#222222",
        "text.color": "#222222",
        "xtick.color": "#444444",
        "ytick.color": "#444444",
        "axes.grid": True,
        "grid.color": "#dddddd",
        "grid.linewidth": 0.6,
        "font.size": 11,
    }
)


def season_label(date: pd.Timestamp) -> str:
    # month >= 8, not >= 7: the COVID-delayed 2019/20 season ran to
    # 2020-07-26, and a >= 7 cutoff would misfile those July fixtures into
    # "2020/21". EPL seasons never start in July, so an 8 cutoff is safe.
    year = date.year if date.month >= 8 else date.year - 1
    return f"{year}/{(year + 1) % 100:02d}"


def load_bets(conn: sqlite3.Connection) -> pd.DataFrame:
    # ORDER BY date, id: deterministic tiebreak for same-date rows, matching
    # engine.summarize()'s query -- see the comment there.
    df = pd.read_sql_query(
        "SELECT * FROM backtest_bets WHERE date >= ? AND date <= ? ORDER BY date, id",
        conn,
        params=(START, END),
    )
    df["date"] = pd.to_datetime(df["date"])
    df["season"] = df["date"].apply(season_label)
    return df


def stats_table(df: pd.DataFrame, group_col: str | None) -> pd.DataFrame:
    """total_bets, roi, hit_rate, max_drawdown, avg_clv_pct, pct_positive_clv
    -- overall or grouped by group_col."""
    groups = [(None, df)] if group_col is None else list(df.groupby(group_col))

    rows = []
    for key, group in groups:
        staked = group["kelly_stake"].sum()
        pnl = group["pnl_units"].sum()
        roi = pnl / staked if staked else 0.0
        hit_rate = (group["outcome"] == group["actual_result"]).mean()
        # kind="stable": pandas' default quicksort isn't stable, and would
        # otherwise reorder same-date ties arbitrarily -- shifting the
        # intra-day cumulative trajectory and giving a max_drawdown that
        # silently disagrees with engine.summarize()'s (which relies on the
        # SQL ORDER BY date and never re-sorts). group is already date-order
        # from load_bets()'s query; this re-sort is just a defensive no-op
        # in the common case, made explicit and reproducible either way.
        cumulative = group.sort_values("date", kind="stable")["pnl_units"].cumsum()
        max_dd = (cumulative.cummax() - cumulative).max() if len(cumulative) else 0.0
        clv = group["clv_pct"].dropna()
        row = {
            "total_bets": len(group),
            "roi": roi,
            "hit_rate": hit_rate,
            "max_drawdown": max_dd,
            "avg_clv_pct": float(clv.mean()) if len(clv) else 0.0,
            "pct_positive_clv": float((clv > 0).mean()) if len(clv) else 0.0,
        }
        if key is not None:
            row[group_col] = key
        rows.append(row)

    out = pd.DataFrame(rows)
    cols = ["total_bets", "roi", "hit_rate", "max_drawdown", "avg_clv_pct", "pct_positive_clv"]
    if group_col is not None:
        cols = [group_col, *cols]
    return out[cols]


def to_markdown_table(df: pd.DataFrame, headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    # Use to_dict("records") rather than iterrows(): iterrows() coerces each
    # row to a single common dtype, silently turning an int total_bets into
    # a float (e.g. 1821 -> 1821.0) whenever it shares a row with float
    # columns and no string column is present to force dtype=object instead.
    for record in df.to_dict("records"):
        cells = []
        for col in df.columns:
            val = record[col]
            if col == "roi":
                cells.append(f"{val:+.2%}")
            elif col == "hit_rate":
                cells.append(f"{val:.1%}")
            elif col == "max_drawdown":
                cells.append(f"{val:.2f}")
            elif col == "avg_clv_pct":
                cells.append(f"{val:+.2f}%")
            elif col == "pct_positive_clv":
                cells.append(f"{val:.1%}")
            elif col == "total_bets":
                cells.append(str(int(val)))
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def plot_cumulative_pnl(df: pd.DataFrame, path: Path) -> None:
    daily = df.sort_values("date").groupby("date")["pnl_units"].sum().cumsum()

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(daily.index, daily.values, color="#1f4e79", linewidth=1.4)
    ax.axhline(0, color="#b02a2a", linewidth=0.9, linestyle="--")
    ax.set_title(f"Cumulative P&L, flagged bets ({START} to {END}, edge > 3%)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative P&L (units)")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_roi_by_threshold(sweep_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(
        sweep_df["edge_threshold"] * 100,
        sweep_df["roi"] * 100,
        marker="o",
        color="#1f4e79",
        linewidth=1.4,
    )
    ax.axhline(0, color="#b02a2a", linewidth=0.9, linestyle="--")
    ax.set_title(f"ROI vs. edge threshold ({START} to {END})")
    ax.set_xlabel("Edge threshold (%)")
    ax.set_ylabel("ROI (%)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    settings = load_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    # Idempotent (CREATE TABLE IF NOT EXISTS): makes this script runnable
    # standalone against a fresh DB, and self-healing after a schema-change
    # migration that dropped backtest_bets (as happened during Phase 2).
    init_db(conn)

    ASSETS_DIR.mkdir(exist_ok=True)

    if conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0] == 0:
        raise SystemExit(
            "historical_matches is empty -- run "
            "`uv run ev-finder ingest-historical --seasons 2019-2024` first."
        )

    # 1. Default-threshold run: source for the headline numbers, the
    #    cumulative P&L chart, and the by-season / by-market tables.
    run_backtest(conn, start=START, end=END, edge_threshold=DEFAULT_EDGE)
    default_bets = load_bets(conn)

    overall = stats_table(default_bets, group_col=None)
    by_season = stats_table(default_bets, group_col="season").sort_values("season")
    by_market = stats_table(default_bets, group_col="market").sort_values("market")

    plot_cumulative_pnl(default_bets, ASSETS_DIR / "cumulative_pnl.png")

    # 2. Threshold sweep: overall stats at each edge threshold.
    sweep_rows = []
    for edge in THRESHOLD_SWEEP:
        summary = run_backtest(conn, start=START, end=END, edge_threshold=edge)
        sweep_rows.append(
            {
                "edge_threshold": edge,
                "total_bets": summary.total_bets,
                "roi": summary.roi,
                "hit_rate": summary.hit_rate,
                "max_drawdown": summary.max_drawdown,
                "avg_clv_pct": summary.avg_clv_pct if summary.avg_clv_pct is not None else 0.0,
                "pct_positive_clv": (
                    summary.pct_positive_clv if summary.pct_positive_clv is not None else 0.0
                ),
            }
        )
    sweep_df = pd.DataFrame(sweep_rows)
    plot_roi_by_threshold(sweep_df, ASSETS_DIR / "roi_by_threshold.png")

    sweep_display = sweep_df.copy()
    sweep_display["edge_threshold"] = sweep_display["edge_threshold"].apply(lambda e: f"{e:.0%}")
    sweep_display = sweep_display.rename(columns={"edge_threshold": "edge_threshold_pct"})

    # 3. Restore the DB to the default-threshold run so it matches the
    #    headline numbers quoted in README.md / RESULTS.md.
    run_backtest(conn, start=START, end=END, edge_threshold=DEFAULT_EDGE)
    conn.close()

    # 4. Write RESULTS.md.
    metric_headers = [
        "total_bets",
        "roi",
        "hit_rate",
        "max_drawdown",
        "avg_clv",
        "pct_positive_clv",
    ]
    lines = [
        "# Results",
        "",
        f"Walk-forward backtest, {START} to {END}, Bet365 pre-closing odds "
        "(the price realistically available at decision time -- see README Method), "
        f"quarter Kelly staking (fraction={DEFAULT_KELLY_FRACTION}). "
        "All measured quantities below (bet counts, ROI, hit rate, max drawdown, CLV) come "
        "directly from this backtest run; any interpretation of what they mean is in README.md, "
        "not here.\n\n"
        "CLV = closing-line value: `(bet_price / true_closing_price - 1) * 100`, where "
        "bet_price is the pre-closing price the bet was actually decided and staked on, and "
        'true_closing_price (Bet365\'s "C"-suffixed columns) is used *only* for this '
        "diagnostic, never for the bet decision itself. Computed only for bets where "
        "football-data.co.uk has both snapshots (all bets in this backtest window have both).",
        "",
        "## Overall (edge threshold > 3%)",
        "",
        to_markdown_table(overall, metric_headers),
        "",
        "## By season (edge threshold > 3%)",
        "",
        to_markdown_table(by_season, ["season", *metric_headers]),
        "",
        "## By market (edge threshold > 3%)",
        "",
        to_markdown_table(by_market, ["market", *metric_headers]),
        "",
        "## By edge threshold",
        "",
        to_markdown_table(sweep_display, ["edge_threshold_pct", *metric_headers]),
        "",
    ]
    RESULTS_PATH.write_text("\n".join(lines))

    print(f"Wrote {RESULTS_PATH}")
    print(f"Wrote {ASSETS_DIR / 'cumulative_pnl.png'}")
    print(f"Wrote {ASSETS_DIR / 'roi_by_threshold.png'}")


if __name__ == "__main__":
    main()
