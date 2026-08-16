from __future__ import annotations

import pytest

from ev_finder.backtest.engine import fractional_kelly_stake


def test_zero_stake_when_no_edge():
    # Implied prob from odds 2.0 is 0.5; model thinks 0.4 -- no edge.
    assert fractional_kelly_stake(model_prob=0.4, decimal_odds=2.0) == 0.0


def test_zero_stake_when_edge_exactly_zero():
    # model_prob exactly equals the break-even probability (1/odds).
    assert fractional_kelly_stake(model_prob=0.5, decimal_odds=2.0) == 0.0


def test_positive_stake_when_edge_positive():
    # Implied prob from odds 3.0 is 1/3; model thinks 0.4 -- positive edge.
    # b = 2.0, full Kelly = (2*0.4 - 0.6) / 2 = 0.1, quarter-Kelly = 0.025.
    stake = fractional_kelly_stake(model_prob=0.4, decimal_odds=3.0, kelly_fraction=0.25)
    assert stake == pytest.approx(0.025)


def test_kelly_fraction_scales_stake_linearly():
    full = fractional_kelly_stake(model_prob=0.4, decimal_odds=3.0, kelly_fraction=1.0)
    half = fractional_kelly_stake(model_prob=0.4, decimal_odds=3.0, kelly_fraction=0.5)
    assert half == pytest.approx(full / 2)


def test_stake_never_negative_for_bad_odds():
    assert fractional_kelly_stake(model_prob=0.9, decimal_odds=1.0) == 0.0
