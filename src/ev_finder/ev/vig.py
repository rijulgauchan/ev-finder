"""Vig (bookmaker margin) removal.

Bookmaker decimal odds imply probabilities that sum to more than 1 -- the
excess is the "vig"/overround. This module removes it using the
multiplicative method: convert odds to implied probabilities, then
normalize so they sum to exactly 1.
"""

from __future__ import annotations


def remove_vig(decimal_odds: list[float]) -> list[float]:
    """Convert a market's decimal odds into vig-free (fair) probabilities.

    Uses the multiplicative method: p_i = (1/odds_i) / sum(1/odds_j).

    Args:
        decimal_odds: Decimal odds for every outcome in one market
            (e.g. [2.5, 3.4, 2.9] for a 1X2 market). Must contain at least
            two outcomes, each strictly greater than 1.0.

    Returns:
        Fair (vig-free) probabilities in the same order as the input,
        summing to 1.0.

    Raises:
        ValueError: if `decimal_odds` has fewer than two entries, or any
            odds value is not strictly greater than 1.0.
    """
    if len(decimal_odds) < 2:
        raise ValueError("remove_vig requires at least two outcomes")
    if any(odds <= 1.0 for odds in decimal_odds):
        raise ValueError("decimal odds must be strictly greater than 1.0")

    implied_probs = [1.0 / odds for odds in decimal_odds]
    overround = sum(implied_probs)
    return [p / overround for p in implied_probs]
