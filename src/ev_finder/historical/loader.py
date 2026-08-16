"""Parse football-data.co.uk season CSVs and load them into `historical_matches`."""

from __future__ import annotations

import io
import sqlite3

import pandas as pd

# Maps our column names to the source CSV's column names. Some older seasons
# may be missing a column (e.g. an odds field) -- those are treated as NULL
# rather than failing the whole load.
#
# football-data.co.uk's un-suffixed odds columns (B365H, PSH, Avg>2.5, ...)
# are PRE-CLOSING odds -- an earlier snapshot, not the price at kickoff.
# True closing odds use a "C" suffix (B365CH, PSCH, AvgC>2.5, ...). See
# https://www.football-data.co.uk/notes.txt. Both are ingested: pre-closing
# is what the backtest's bet decision (edge, staking, settlement) is driven
# by -- it's the price actually available at decision time -- while closing
# is used only afterward, as the CLV reference point.
COLUMN_MAP = {
    "date": "Date",
    "home_team": "HomeTeam",
    "away_team": "AwayTeam",
    "home_goals": "FTHG",
    "away_goals": "FTAG",
    "ftr": "FTR",
    "b365_h": "B365H",
    "b365_d": "B365D",
    "b365_a": "B365A",
    "ps_h": "PSH",
    "ps_d": "PSD",
    "ps_a": "PSA",
    "avg_h": "AvgH",
    "avg_d": "AvgD",
    "avg_a": "AvgA",
    "b365_over_2_5": "B365>2.5",
    "b365_under_2_5": "B365<2.5",
    "avg_over_2_5": "Avg>2.5",
    "avg_under_2_5": "Avg<2.5",
    "b365_close_h": "B365CH",
    "b365_close_d": "B365CD",
    "b365_close_a": "B365CA",
    "ps_close_h": "PSCH",
    "ps_close_d": "PSCD",
    "ps_close_a": "PSCA",
    "avg_close_h": "AvgCH",
    "avg_close_d": "AvgCD",
    "avg_close_a": "AvgCA",
    "b365_close_over_2_5": "B365C>2.5",
    "b365_close_under_2_5": "B365C<2.5",
    "avg_close_over_2_5": "AvgC>2.5",
    "avg_close_under_2_5": "AvgC<2.5",
}

REQUIRED_COLUMNS = ["date", "home_team", "away_team", "home_goals", "away_goals", "ftr"]

INSERT_SQL = f"""
INSERT OR IGNORE INTO historical_matches
    ({", ".join(COLUMN_MAP.keys())})
VALUES
    ({", ".join("?" for _ in COLUMN_MAP)})
"""


def parse_csv(csv_text: str) -> pd.DataFrame:
    """Parse a raw football-data.co.uk CSV into a normalized DataFrame.

    Column names are normalized to `COLUMN_MAP`'s keys; missing source columns
    become all-NaN columns instead of raising. Rows missing any required
    field (date/teams/goals/result) are dropped.
    """
    raw = pd.read_csv(io.StringIO(csv_text))

    df = pd.DataFrame()
    for our_col, source_col in COLUMN_MAP.items():
        df[our_col] = raw[source_col] if source_col in raw.columns else pd.NA

    df = df.dropna(subset=REQUIRED_COLUMNS)

    # Source dates are dd/mm/yy or dd/mm/yyyy depending on season; normalize
    # to ISO 8601 so SQLite text comparisons sort/compare correctly.
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, format="mixed").dt.strftime("%Y-%m-%d")
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)

    return df.reset_index(drop=True)


def load_dataframe(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insert parsed match rows into `historical_matches`, skipping duplicates.

    Returns the number of rows actually inserted (existing rows, matched on
    the (date, home_team, away_team) UNIQUE constraint, are silently skipped).
    """
    inserted = 0
    cols = list(COLUMN_MAP.keys())
    # sqlite3 can't bind pandas' NA/NaN sentinels -- convert them to plain
    # None so missing odds columns are stored as SQL NULL.
    clean = df[cols].astype(object).where(df[cols].notna(), None)
    for row in clean.itertuples(index=False, name=None):
        cursor = conn.execute(INSERT_SQL, row)
        inserted += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    conn.commit()
    return inserted
