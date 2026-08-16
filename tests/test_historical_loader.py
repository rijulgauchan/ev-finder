from __future__ import annotations

from ev_finder.historical.fetch import season_code
from ev_finder.historical.loader import load_dataframe, parse_csv

# Minimal fixture CSV: 3 rows, dd/mm/yy dates, all target columns present.
SAMPLE_CSV = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,PSH,PSD,PSA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,Avg>2.5,Avg<2.5
E0,11/08/23,Arsenal,Chelsea,2,1,H,2.10,3.40,3.60,2.05,3.45,3.70,2.08,3.42,3.65,1.90,1.95,1.88,1.97
E0,12/08/23,Everton,Fulham,1,1,D,2.50,3.20,2.90,2.45,3.25,2.95,2.48,3.22,2.92,2.10,1.75,2.05,1.78
E0,13/08/23,Newcastle,Aston Villa,0,2,A,1.80,3.60,4.50,1.78,3.65,4.60,1.79,3.62,4.55,1.85,2.00,1.83,1.98
"""


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
    # Older-style CSV missing the Pinnacle and totals columns entirely.
    minimal_csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "E0,01/09/23,Brentford,Burnley,3,0,H,1.70,3.80,5.00\n"
    )
    df = parse_csv(minimal_csv)
    inserted = load_dataframe(db_conn, df)

    assert inserted == 1
    row = db_conn.execute("SELECT ps_h, avg_over_2_5 FROM historical_matches").fetchone()
    assert row["ps_h"] is None
    assert row["avg_over_2_5"] is None
