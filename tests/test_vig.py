from __future__ import annotations

import pytest

from ev_finder.ev.vig import remove_vig


def test_three_way_market_sums_to_one():
    # Typical 1X2 market with ~5% overround.
    probs = remove_vig([2.10, 3.40, 3.60])
    assert sum(probs) == pytest.approx(1.0)
    assert all(0.0 < p < 1.0 for p in probs)


def test_two_way_market_sums_to_one():
    probs = remove_vig([1.90, 1.95])
    assert sum(probs) == pytest.approx(1.0)


def test_preserves_relative_order_and_ranking():
    # The shortest-priced (most likely) outcome should end up with the
    # highest fair probability, and order must be preserved.
    odds = [2.10, 3.40, 3.60]
    probs = remove_vig(odds)
    assert probs[0] > probs[1] > probs[2]


def test_fair_odds_are_a_no_op():
    # Odds with zero overround (implied probs already sum to 1) should be
    # returned unchanged (within floating point tolerance).
    fair_odds = [2.0, 2.0]  # 0.5 + 0.5 = 1.0, no vig
    probs = remove_vig(fair_odds)
    assert probs == pytest.approx([0.5, 0.5])


def test_known_overround_removed_correctly():
    # 1.8/1.8 implies 111.1% overround; symmetric market so fair split is 50/50
    # once the vig is stripped out, even though raw implied probs summed >1.
    vigged_probs = remove_vig([1.8, 1.8])
    assert sum(vigged_probs) == pytest.approx(1.0)
    assert vigged_probs == pytest.approx([0.5, 0.5])


def test_raises_on_too_few_outcomes():
    with pytest.raises(ValueError):
        remove_vig([2.0])


def test_raises_on_empty_list():
    with pytest.raises(ValueError):
        remove_vig([])


@pytest.mark.parametrize("bad_odds", [[1.0, 3.0], [0.5, 3.0], [-2.0, 3.0]])
def test_raises_on_invalid_odds(bad_odds):
    with pytest.raises(ValueError):
        remove_vig(bad_odds)
