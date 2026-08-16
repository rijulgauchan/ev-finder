from __future__ import annotations

from ev_finder.historical.fetch import season_code
from ev_finder.historical.loader import load_dataframe, parse_csv

# Minimal fixture CSV: 3 rows, dd/mm/yy dates, both pre-closing and closing
# ("C"-suffixed) odds columns present.
SAMPLE_CSV = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
    "B365H,B365D,B365A,PSH,PSD,PSA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,Avg>2.5,Avg<2.5,"
    "B365CH,B365CD,B365CA,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,AvgC>2.5,AvgC<2.5\n"
    "E0,11/08/23,Arsenal,Chelsea,2,1,H,"
    "2.10,3.40,3.60,2.05,3.45,3.70,2.08,3.42,3.65,1.90,1.95,1.88,1.97,"
    "2.05,3.50,3.70,2.02,3.55,3.75,2.04,3.48,3.72,1.92,1.93,1.90,1.95\n"
    "E0,12/08/23,Everton,Fulham,1,1,D,"
    "2.50,3.20,2.90,2.45,3.25,2.95,2.48,3.22,2.92,2.10,1.75,2.05,1.78,"
    "2.45,3.25,2.95,2.42,3.30,3.00,2.44,3.24,2.94,2.05,1.80,2.00,1.83\n"
    "E0,13/08/23,Newcastle,Aston Villa,0,2,A,"
    "1.80,3.60,4.50,1.78,3.65,4.60,1.79,3.62,4.55,1.85,2.00,1.83,1.98,"
    "1.75,3.70,4.70,1.74,3.72,4.75,1.76,3.68,4.68,1.80,2.05,1.79,2.02\n"
)


def test_season_code_maps_start_year_correctly():
    assert season_code(2019) == "1920"
    assert season_code(2024) == "2425"
    assert season_code(1999) == "9900"


def test_parse_csv_normalizes_columns_and_dates():
    df = parse_csv(SAMPLE_CSV)

    assert len(df) == 3
    assert list(df["date"]) == ["2023-08-11", "2023-08-12", "2023-08-13"]
    assert df.loc[0, "home_team"] == "Arsenal"
    assert df.loc[0, "away_team"] == "Chelsea"
    assert int(df.loc[0, "home_goals"]) == 2
    assert int(df.loc[0, "away_goals"]) == 1
    assert df.loc[0, "ftr"] == "H"
    assert df.loc[0, "b365_h"] == 2.10
    assert df.loc[0, "b365_over_2_5"] == 1.90
    assert df.loc[0, "avg_under_2_5"] == 1.97
    # closing ("C"-suffixed) columns parse into their own, separate fields
    assert df.loc[0, "b365_close_h"] == 2.05
    assert df.loc[0, "b365_close_over_2_5"] == 1.92
    assert df.loc[0, "ps_close_a"] == 3.75


def test_load_dataframe_inserts_all_rows(db_conn):
    df = parse_csv(SAMPLE_CSV)
    inserted = load_dataframe(db_conn, df)

    assert inserted == 3
    count = db_conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0]
    assert count == 3


def test_load_dataframe_is_idempotent_on_rerun(db_conn):
    df = parse_csv(SAMPLE_CSV)
    first_inserted = load_dataframe(db_conn, df)
    second_inserted = load_dataframe(db_conn, df)

    assert first_inserted == 3
    assert second_inserted == 0
    count = db_conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0]
    assert count == 3


def test_load_dataframe_handles_missing_odds_columns(db_conn):
    # Older-style CSV missing the Pinnacle, totals, and closing columns
    # entirely (only pre-closing Bet365 1X2 present).
    minimal_csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "E0,01/09/23,Brentford,Burnley,3,0,H,1.70,3.80,5.00\n"
    )
    df = parse_csv(minimal_csv)
    inserted = load_dataframe(db_conn, df)

    assert inserted == 1
    row = db_conn.execute(
        "SELECT ps_h, avg_over_2_5, b365_close_h, ps_close_h FROM historical_matches"
    ).fetchone()
    assert row["ps_h"] is None
    assert row["avg_over_2_5"] is None
    assert row["b365_close_h"] is None
    assert row["ps_close_h"] is None
