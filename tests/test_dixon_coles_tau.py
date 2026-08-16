from __future__ import annotations

import pytest

from ev_finder.model.dixon_coles import tau


@pytest.mark.parametrize("lam,mu", [(1.2, 1.0), (0.8, 1.5), (2.0, 0.6)])
def test_tau_greater_than_one_at_0_0_and_1_1_when_rho_negative(lam, mu):
    rho = -0.15
    assert tau(0, 0, lam, mu, rho) > 1.0
    assert tau(1, 1, lam, mu, rho) > 1.0


@pytest.mark.parametrize("lam,mu", [(1.2, 1.0), (0.8, 1.5), (2.0, 0.6)])
def test_tau_less_than_one_at_0_1_and_1_0_when_rho_negative(lam, mu):
    rho = -0.15
    assert tau(0, 1, lam, mu, rho) < 1.0
    assert tau(1, 0, lam, mu, rho) < 1.0


def test_tau_is_one_elsewhere():
    rho = -0.15
    for x, y in [(2, 0), (0, 2), (2, 2), (3, 1), (1, 3), (5, 5)]:
        assert tau(x, y, 1.2, 1.0, rho) == 1.0


def test_tau_is_identity_when_rho_zero():
    for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        assert tau(x, y, 1.2, 1.0, 0.0) == 1.0


def test_tau_signs_flip_when_rho_positive():
    rho = 0.15
    assert tau(0, 0, 1.2, 1.0, rho) < 1.0
    assert tau(1, 1, 1.2, 1.0, rho) < 1.0
    assert tau(0, 1, 1.2, 1.0, rho) > 1.0
    assert tau(1, 0, 1.2, 1.0, rho) > 1.0
