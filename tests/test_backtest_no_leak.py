"""Guarantees that DixonColesModel.fit(matches, as_of_date=D) never uses a
row with date >= D. This is the single most important correctness property
for the backtest: if it doesn't hold, every backtest result is contaminated
with hindsight and the ROI/hit-rate numbers are meaningless.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ev_finder.model.dixon_coles import DixonColesModel

CUTOFF = "2023-01-01"

CLEAN_PAST_ROWS = [
    {"date": "2022-12-01", "home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 1},
    {"date": "2022-12-05", "home_team": "C", "away_team": "D", "home_goals": 0, "away_goals": 0},
    {"date": "2022-12-10", "home_team": "B", "away_team": "C", "home_goals": 1, "away_goals": 1},
    {"date": "2022-12-15", "home_team": "D", "away_team": "A", "home_goals": 3, "away_goals": 2},
    {"date": "2022-12-20", "home_team": "A", "away_team": "C", "home_goals": 1, "away_goals": 0},
    {"date": "2022-12-25", "home_team": "B", "away_team": "D", "home_goals": 2, "away_goals": 2},
]

# Deliberately implausible values, and dates >= CUTOFF (including exactly
# on the boundary) plus a team ("Ghost FC") that never appears in the past
# rows at all. If fit() leaked any of this in, the result would visibly
# blow up or "Ghost FC" would show up in the fitted team list.
POISONED_FUTURE_ROWS = [
    # exactly on the cutoff boundary -- must be excluded (date < D, not <=)
    {"date": CUTOFF, "home_team": "A", "away_team": "B", "home_goals": 99, "away_goals": 0},
    {"date": "2023-01-02", "home_team": "C", "away_team": "D", "home_goals": 0, "away_goals": 99},
    {
        "date": "2023-06-01",
        "home_team": "Ghost FC",
        "away_team": "A",
        "home_goals": 500,
        "away_goals": 500,
    },
]


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_fit_matches_a_clean_prefiltered_fit():
    """fit(everything, as_of_date=D) must equal fit(only-past-rows, as_of_date=far_future)."""
    full_df = _make_df(CLEAN_PAST_ROWS + POISONED_FUTURE_ROWS)
    past_only_df = _make_df(CLEAN_PAST_ROWS)

    model_full = DixonColesModel(xi=0.0).fit(full_df, as_of_date=CUTOFF)
    model_clean = DixonColesModel(xi=0.0).fit(past_only_df, as_of_date="2099-01-01")

    assert model_full.teams_ == model_clean.teams_
    assert "Ghost FC" not in model_full.teams_
    np.testing.assert_array_equal(model_full.alpha_, model_clean.alpha_)
    np.testing.assert_array_equal(model_full.beta_, model_clean.beta_)
    assert model_full.gamma_ == model_clean.gamma_
    assert model_full.rho_ == model_clean.rho_


def test_boundary_row_on_as_of_date_is_excluded():
    """A row dated exactly `as_of_date` must not be included (date < D, not <=)."""
    boundary_row = {
        "date": CUTOFF,
        "home_team": "A",
        "away_team": "B",
        "home_goals": 500,
        "away_goals": 0,
    }
    with_boundary = _make_df(CLEAN_PAST_ROWS + [boundary_row])
    without_boundary = _make_df(CLEAN_PAST_ROWS)

    model_with = DixonColesModel(xi=0.0).fit(with_boundary, as_of_date=CUTOFF)
    model_without = DixonColesModel(xi=0.0).fit(without_boundary, as_of_date=CUTOFF)

    np.testing.assert_array_equal(model_with.alpha_, model_without.alpha_)
    np.testing.assert_array_equal(model_with.beta_, model_without.beta_)


def test_fit_raises_if_nothing_is_before_as_of_date():
    df = _make_df(POISONED_FUTURE_ROWS)
    with pytest.raises(ValueError, match="No matches before as_of_date"):
        DixonColesModel().fit(df, as_of_date=CUTOFF)
