from __future__ import annotations

import math

import pytest

from ev_finder.backtest.engine import _evaluate_market, clv_pct


def test_evaluate_market_skips_when_decision_odds_are_none():
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.9, "under_2_5": 0.1},
        outcomes=["over_2_5", "under_2_5"],
        decision_odds=[None, 1.95],
        closing_reference_odds=[1.80, 2.00],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows == []


def test_evaluate_market_skips_when_decision_odds_are_nan():
    # Regression test: pandas.read_sql_query turns SQL NULL into NaN (not
    # None) for float columns, and SQLite treats a bound NaN as NULL for
    # NOT NULL columns -- so this case must be caught here, not surfaced
    # later as an IntegrityError on insert.
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.9, "under_2_5": 0.1},
        outcomes=["over_2_5", "under_2_5"],
        decision_odds=[math.nan, 1.95],
        closing_reference_odds=[1.80, 2.00],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows == []


def test_evaluate_market_skips_when_decision_odds_are_zero():
    # Regression test: football-data.co.uk sometimes encodes "missing" as a
    # literal 0 rather than a blank cell (e.g. 2021-12-19 Newcastle vs Man
    # City's closing totals -- the equivalent bug for decision odds hasn't
    # been observed in this dataset, but the guard applies uniformly). 0
    # isn't a valid decimal price -- remove_vig would reject it -- so it
    # must be filtered the same as missing/NaN.
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.9, "under_2_5": 0.1},
        outcomes=["over_2_5", "under_2_5"],
        decision_odds=[0.0, 0.0],
        closing_reference_odds=[1.80, 2.00],
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
        decision_odds=[1.80, 2.10],
        closing_reference_odds=[1.75, 2.15],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert len(rows) == 1
    assert rows[0]["outcome"] == "over_2_5"
    assert not math.isnan(rows[0]["market_prob_no_vig"])


def test_evaluate_market_computes_clv_when_closing_reference_available():
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.7, "under_2_5": 0.3},
        outcomes=["over_2_5", "under_2_5"],
        decision_odds=[1.80, 2.10],
        closing_reference_odds=[1.75, 2.15],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows[0]["bet_price"] == 1.80
    assert rows[0]["closing_reference_price"] == 1.75
    assert rows[0]["clv_pct"] == pytest.approx(clv_pct(1.80, 1.75))
    assert rows[0]["clv_pct"] > 0  # took a better (higher) price than close


def test_evaluate_market_leaves_clv_null_when_closing_reference_missing():
    rows = _evaluate_market(
        model_probs={"over_2_5": 0.7, "under_2_5": 0.3},
        outcomes=["over_2_5", "under_2_5"],
        decision_odds=[1.80, 2.10],
        closing_reference_odds=[math.nan, 2.15],
        actual_result="over_2_5",
        market="totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    assert rows[0]["closing_reference_price"] is None
    assert rows[0]["clv_pct"] is None


def test_clv_pct_sign_convention():
    # Better (higher) price taken than close -- market moved in the
    # bettor's favor after the bet -- is positive CLV.
    assert clv_pct(bet_price=2.10, closing_reference_price=2.00) > 0
    # Worse (lower) price taken than close -- negative CLV.
    assert clv_pct(bet_price=1.90, closing_reference_price=2.00) < 0
    # Same price -- zero CLV.
    assert clv_pct(bet_price=2.00, closing_reference_price=2.00) == pytest.approx(0.0)


# --- No-future-information-in-the-decision guarantee -----------------------
#
# This is the engine-level analogue of tests/test_backtest_no_leak.py (which
# checks the *model* fit never sees future match results). Here the concern
# is different: even with a leak-free model, the bet *decision* would still
# be compromised if it were benchmarked against the true closing price,
# since that price isn't known until kickoff. These tests assert the
# decision -- whether a bet is flagged, its stake, and its settlement -- is
# a pure function of decision_odds (pre-closing) alone, and is completely
# unaffected by closing_reference_odds, no matter what value it takes.


@pytest.mark.parametrize(
    "corrupted_closing_ref",
    [
        [1.75, 2.15],  # plausible real value
        [None, None],  # missing entirely
        [math.nan, math.nan],  # missing (NaN form)
        [999.0, 0.001],  # wildly implausible, would flip which side "won" the edge
        [1.80, 2.10],  # identical to decision_odds (zero CLV)
    ],
)
def test_decision_is_independent_of_closing_reference_odds(corrupted_closing_ref):
    decision_odds = [1.80, 2.10]
    model_probs = {"over_2_5": 0.7, "under_2_5": 0.3}

    baseline = _evaluate_market(
        model_probs,
        ["over_2_5", "under_2_5"],
        decision_odds,
        [1.75, 2.15],  # some baseline closing reference
        "over_2_5",
        "totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )
    corrupted = _evaluate_market(
        model_probs,
        ["over_2_5", "under_2_5"],
        decision_odds,
        corrupted_closing_ref,
        "over_2_5",
        "totals",
        edge_threshold=0.03,
        kelly_fraction=0.25,
    )

    assert len(baseline) == len(corrupted)
    for b, c in zip(baseline, corrupted, strict=True):
        # Everything that constitutes "the decision" must match exactly,
        # regardless of what closing_reference_odds was.
        assert b["outcome"] == c["outcome"]
        assert b["model_prob"] == c["model_prob"]
        assert b["market_prob_no_vig"] == c["market_prob_no_vig"]
        assert b["edge"] == c["edge"]
        assert b["kelly_stake"] == c["kelly_stake"]
        assert b["pnl_units"] == c["pnl_units"]
        assert b["bet_price"] == c["bet_price"]
        # Only the CLV-related fields are allowed to differ.
