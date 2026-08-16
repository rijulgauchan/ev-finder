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
    year = date.year if date.month >= 7 else date.year - 1
    return f"{year}/{(year + 1) % 100:02d}"


def load_bets(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM backtest_bets WHERE date >= ? AND date <= ? ORDER BY date",
        conn,
        params=(START, END),
    )
    df["date"] = pd.to_datetime(df["date"])
    df["season"] = df["date"].apply(season_label)
    return df


def stats_table(df: pd.DataFrame, group_col: str | None) -> pd.DataFrame:
    """total_bets, roi, hit_rate, max_drawdown -- overall or grouped by group_col."""
    groups = [(None, df)] if group_col is None else list(df.groupby(group_col))

    rows = []
    for key, group in groups:
        staked = group["kelly_stake"].sum()
        pnl = group["pnl_units"].sum()
        roi = pnl / staked if staked else 0.0
        hit_rate = (group["outcome"] == group["actual_result"]).mean()
        cumulative = group.sort_values("date")["pnl_units"].cumsum()
        max_dd = (cumulative.cummax() - cumulative).max() if len(cumulative) else 0.0
        row = {
            "total_bets": len(group),
            "roi": roi,
            "hit_rate": hit_rate,
            "max_drawdown": max_dd,
        }
        if key is not None:
            row[group_col] = key
        rows.append(row)

    out = pd.DataFrame(rows)
    if group_col is not None:
        out = out[[group_col, "total_bets", "roi", "hit_rate", "max_drawdown"]]
    return out


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

    ASSETS_DIR.mkdir(exist_ok=True)

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
    lines = [
        "# Results",
        "",
        f"Walk-forward backtest, {START} to {END}, Bet365 closing odds, "
        f"quarter Kelly staking (fraction={DEFAULT_KELLY_FRACTION}).",
        "",
        "## Overall (edge threshold > 3%)",
        "",
        to_markdown_table(overall, ["total_bets", "roi", "hit_rate", "max_drawdown"]),
        "",
        "## By season (edge threshold > 3%)",
        "",
        to_markdown_table(by_season, ["season", "total_bets", "roi", "hit_rate", "max_drawdown"]),
        "",
        "## By market (edge threshold > 3%)",
        "",
        to_markdown_table(by_market, ["market", "total_bets", "roi", "hit_rate", "max_drawdown"]),
        "",
        "## By edge threshold",
        "",
        to_markdown_table(
            sweep_display,
            ["edge_threshold_pct", "total_bets", "roi", "hit_rate", "max_drawdown"],
        ),
        "",
    ]
    RESULTS_PATH.write_text("\n".join(lines))

    print(f"Wrote {RESULTS_PATH}")
    print(f"Wrote {ASSETS_DIR / 'cumulative_pnl.png'}")
    print(f"Wrote {ASSETS_DIR / 'roi_by_threshold.png'}")


if __name__ == "__main__":
    main()
