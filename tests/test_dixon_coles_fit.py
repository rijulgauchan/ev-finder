from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ev_finder.model.dixon_coles import DixonColesModel

N_TEAMS = 8
N_SEASONS = 800
TEAMS = [f"Team_{i}" for i in range(N_TEAMS)]

# Sums to N_TEAMS exactly (symmetric around 1.0), matching the model's own
# sum(alpha) == n identifiability normalization, so fitted and true values
# are directly comparable without any extra rescaling. Kept moderate (not
# an extreme spread) so the weakest team's low goal-rate doesn't dominate
# the relative-error tolerance with pure sampling noise.
TRUE_ALPHA = np.linspace(0.6, 1.4, N_TEAMS)
TRUE_BETA = np.linspace(0.7, 1.3, N_TEAMS)
TRUE_GAMMA = 1.35


def _simulate_matches(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    day = 0
    for _season in range(N_SEASONS):
        for i in range(N_TEAMS):
            for j in range(N_TEAMS):
                if i == j:
                    continue
                lam = TRUE_ALPHA[i] * TRUE_BETA[j] * TRUE_GAMMA
                mu = TRUE_ALPHA[j] * TRUE_BETA[i]
                home_goals = rng.poisson(lam)
                away_goals = rng.poisson(mu)
                rows.append(
                    {
                        "date": pd.Timestamp("2015-01-01") + pd.Timedelta(days=day),
                        "home_team": TEAMS[i],
                        "away_team": TEAMS[j],
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                    }
                )
                day += 1
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def fitted_model() -> DixonColesModel:
    matches = _simulate_matches()
    as_of_date = matches["date"].max() + pd.Timedelta(days=1)
    # xi=0: no time-decay, so every synthetic match (irrespective of its
    # arbitrary assigned date) contributes equally -- isolates parameter
    # recovery from decay-weighting behavior, which isn't what this test
    # is checking.
    model = DixonColesModel(xi=0.0)
    model.fit(matches, as_of_date=as_of_date)
    return model


def test_teams_recovered(fitted_model):
    assert fitted_model.teams_ == TEAMS


def test_attack_strengths_within_5_percent(fitted_model):
    np.testing.assert_allclose(fitted_model.alpha_, TRUE_ALPHA, rtol=0.05)


def test_defense_strengths_within_5_percent(fitted_model):
    np.testing.assert_allclose(fitted_model.beta_, TRUE_BETA, rtol=0.05)


def test_attack_sums_to_n_teams(fitted_model):
    assert fitted_model.alpha_.sum() == pytest.approx(N_TEAMS, rel=1e-6)
