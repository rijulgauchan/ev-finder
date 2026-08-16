from __future__ import annotations

import math

from ev_finder.backtest.engine import _evaluate_market


def test_evaluate_market_skips_when_odds_are_none():
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.9, "under_2_5": 0.1},
        outcomes=["over_2_5", "under_2_5"],
        odds=[None, 1.95],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows == []


def test_evaluate_market_skips_when_odds_are_nan():
    # Regression test: pandas.read_sql_query turns SQL NULL into NaN (not
    # None) for float columns, and SQLite treats a bound NaN as NULL for
    # NOT NULL columns -- so this case must be caught here, not surfaced
    # later as an IntegrityError on insert.
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.9, "under_2_5": 0.1},
        outcomes=["over_2_5", "under_2_5"],
        odds=[math.nan, 1.95],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows == []


def test_evaluate_market_flags_when_edge_exceeds_threshold():
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.7, "under_2_5": 0.3},
        outcomes=["over_2_5", "under_2_5"],
        odds=[1.80, 2.10],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert len(rows) == 1
    assert rows[0]["outcome"] == "over_2_5"
    assert not math.isnan(rows[0]["market_prob_no_vig"])
