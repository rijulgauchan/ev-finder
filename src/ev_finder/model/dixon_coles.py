"""Dixon-Coles (1997) time-weighted Poisson goals model.

Reference: Dixon, M.J. and Coles, S.G. (1997), "Modelling Association
Football Scores and Inefficiencies in the Football Betting Market."

Each team gets a multiplicative attack strength (alpha) and defense
strength (beta). Expected goals are:

    lambda (home goals) = alpha_home * beta_away * gamma
    mu     (away goals) = alpha_away * beta_home

where gamma is a fixed home-advantage multiplier. A single correlation
parameter `rho` adjusts the four low-scoring cells (0-0, 1-0, 0-1, 1-1) via
the `tau` function, correcting for the tendency of low-scoring games to be
drawn more often than independent Poisson processes would predict.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10  # prediction grid covers 0..9 goals per side

_ALPHA_BETA_BOUNDS = (1e-3, 10.0)
_GAMMA_BOUNDS = (1e-3, 5.0)
_RHO_BOUNDS = (-0.99, 0.99)
_DEFAULT_XI = 0.0065


class UnknownTeamError(ValueError):
    """Raised when predicting for a team the model wasn't fitted on."""


def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score correlation adjustment for scoreline (x, y)."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _tau_grid(lam: float, mu: float, rho: float, size: int = MAX_GOALS) -> np.ndarray:
    """Vectorized `tau` over a (size, size) scoreline grid."""
    grid = np.ones((size, size))
    grid[0, 0] = 1.0 - lam * mu * rho
    if size > 1:
        grid[0, 1] = 1.0 + lam * rho
        grid[1, 0] = 1.0 + mu * rho
        grid[1, 1] = 1.0 - rho
    return grid


class DixonColesModel:
    """Fits and predicts with the Dixon-Coles Poisson goals model."""

    def __init__(self, xi: float = _DEFAULT_XI):
        self.xi = xi
        self.teams_: list[str] = []
        self._team_index: dict[str, int] = {}
        self.alpha_: np.ndarray | None = None  # attack strength per team
        self.beta_: np.ndarray | None = None  # defense strength per team
        self.gamma_: float | None = None  # home advantage multiplier
        self.rho_: float | None = None  # low-score correlation

    @property
    def is_fitted(self) -> bool:
        return self.alpha_ is not None

    def fit(
        self,
        matches_df: pd.DataFrame,
        as_of_date,
        warm_start: DixonColesModel | None = None,
    ) -> DixonColesModel:
        """Fit attack/defense/home-advantage/rho on matches strictly before `as_of_date`.

        `as_of_date` bounds the training data: only rows with
        `date < as_of_date` are used. This is deliberately the first thing
        this method does, before anything else touches `matches_df`, so that
        no information from `as_of_date` or later can leak into the fit
        (see tests/test_backtest_no_leak.py).

        `warm_start`, if given, seeds the optimizer with a previously fitted
        model's parameters (for teams in common) to speed up convergence
        during walk-forward backtesting.
        """
        cutoff = pd.Timestamp(as_of_date)
        dates = pd.to_datetime(matches_df["date"])
        train = matches_df.loc[dates < cutoff].copy()
        train_dates = dates.loc[dates < cutoff]

        if train.empty:
            raise ValueError(f"No matches before as_of_date={as_of_date!r} to fit on")

        teams = sorted(set(train["home_team"]) | set(train["away_team"]))
        n = len(teams)
        team_index = {team: i for i, team in enumerate(teams)}

        home_idx = train["home_team"].map(team_index).to_numpy()
        away_idx = train["away_team"].map(team_index).to_numpy()
        home_goals = train["home_goals"].to_numpy(dtype=float)
        away_goals = train["away_goals"].to_numpy(dtype=float)

        days_before = (cutoff - train_dates).dt.days.to_numpy(dtype=float)
        weights = np.exp(-self.xi * np.clip(days_before, a_min=0, a_max=None))

        x0 = self._initial_guess(teams, warm_start)
        bounds = [_ALPHA_BETA_BOUNDS] * n + [_ALPHA_BETA_BOUNDS] * n + [_GAMMA_BOUNDS, _RHO_BOUNDS]

        def neg_log_likelihood(theta: np.ndarray) -> float:
            alpha = theta[:n]
            beta = theta[n : 2 * n]
            gamma, rho = theta[2 * n], theta[2 * n + 1]

            lam = alpha[home_idx] * beta[away_idx] * gamma
            mu = alpha[away_idx] * beta[home_idx]

            tau_vals = np.ones_like(lam)
            m00 = (home_goals == 0) & (away_goals == 0)
            m01 = (home_goals == 0) & (away_goals == 1)
            m10 = (home_goals == 1) & (away_goals == 0)
            m11 = (home_goals == 1) & (away_goals == 1)
            tau_vals[m00] = 1.0 - lam[m00] * mu[m00] * rho
            tau_vals[m01] = 1.0 + lam[m01] * rho
            tau_vals[m10] = 1.0 + mu[m10] * rho
            tau_vals[m11] = 1.0 - rho
            tau_vals = np.clip(tau_vals, 1e-10, None)

            log_lik = (
                np.log(tau_vals) + poisson.logpmf(home_goals, lam) + poisson.logpmf(away_goals, mu)
            )
            return -np.sum(weights * log_lik)

        result = minimize(
            neg_log_likelihood,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 300},
        )

        alpha = result.x[:n]
        beta = result.x[n : 2 * n]
        gamma, rho = result.x[2 * n], result.x[2 * n + 1]

        # Identifiability: rescale so sum(alpha) == n. lambda = alpha_i * beta_j
        # * gamma is invariant under alpha *= k, beta /= k, so this doesn't
        # change the fitted model at all, only its (otherwise arbitrary) scale.
        scale = n / alpha.sum()
        alpha = alpha * scale
        beta = beta / scale

        self.teams_ = teams
        self._team_index = team_index
        self.alpha_ = alpha
        self.beta_ = beta
        self.gamma_ = float(gamma)
        self.rho_ = float(rho)
        return self

    def _initial_guess(self, teams: list[str], warm_start: DixonColesModel | None) -> np.ndarray:
        n = len(teams)
        alpha0 = np.ones(n)
        beta0 = np.ones(n)
        gamma0, rho0 = 1.3, -0.05

        if warm_start is not None and warm_start.is_fitted:
            for i, team in enumerate(teams):
                if team in warm_start._team_index:
                    j = warm_start._team_index[team]
                    alpha0[i] = warm_start.alpha_[j]
                    beta0[i] = warm_start.beta_[j]
            gamma0, rho0 = warm_start.gamma_, warm_start.rho_

        return np.concatenate([alpha0, beta0, [gamma0, rho0]])

    def predict(self, home_team: str, away_team: str) -> np.ndarray:
        """Return a (MAX_GOALS, MAX_GOALS) grid of P(home_goals=i, away_goals=j)."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fit() before predict()")
        for team in (home_team, away_team):
            if team not in self._team_index:
                raise UnknownTeamError(f"Unknown team: {team!r} (not seen during fit)")

        i, j = self._team_index[home_team], self._team_index[away_team]
        lam = self.alpha_[i] * self.beta_[j] * self.gamma_
        mu = self.alpha_[j] * self.beta_[i]

        home_probs = poisson.pmf(np.arange(MAX_GOALS), lam)
        away_probs = poisson.pmf(np.arange(MAX_GOALS), mu)
        grid = np.outer(home_probs, away_probs)
        grid *= _tau_grid(lam, mu, self.rho_, size=MAX_GOALS)
        return grid

    @staticmethod
    def market_probs(grid: np.ndarray) -> dict[str, float]:
        """Collapse a scoreline grid into 1X2 / O-U 2.5 / BTTS probabilities."""
        grid = grid / grid.sum()  # grid is truncated at MAX_GOALS; renormalize
        home_goals_idx, away_goals_idx = np.indices(grid.shape)

        home_win = grid[home_goals_idx > away_goals_idx].sum()
        draw = grid[home_goals_idx == away_goals_idx].sum()
        away_win = grid[home_goals_idx < away_goals_idx].sum()

        total_goals = home_goals_idx + away_goals_idx
        over_2_5 = grid[total_goals >= 3].sum()
        under_2_5 = grid[total_goals < 3].sum()

        btts_yes = grid[(home_goals_idx >= 1) & (away_goals_idx >= 1)].sum()
        btts_no = 1.0 - btts_yes

        return {
            "home_win": float(home_win),
            "draw": float(draw),
            "away_win": float(away_win),
            "over_2_5": float(over_2_5),
            "under_2_5": float(under_2_5),
            "btts_yes": float(btts_yes),
            "btts_no": float(btts_no),
        }
