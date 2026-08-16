# Results

Walk-forward backtest, 2021-08-01 to 2024-05-31, Bet365 pre-closing odds (the price realistically available at decision time -- see README Method), quarter Kelly staking (fraction=0.25). All measured quantities below (bet counts, ROI, hit rate, max drawdown, CLV) come directly from this backtest run; any interpretation of what they mean is in README.md, not here.

CLV = closing-line value: `(bet_price / true_closing_price - 1) * 100`, where bet_price is the pre-closing price the bet was actually decided and staked on, and true_closing_price (Bet365's "C"-suffixed columns) is used *only* for this diagnostic, never for the bet decision itself. Computed only for bets where football-data.co.uk has both snapshots (all bets in this backtest window have both).

## Overall (edge threshold > 3%)

| total_bets | roi | hit_rate | max_drawdown | avg_clv | pct_positive_clv |
|---|---|---|---|---|---|
| 1821 | -6.93% | 44.3% | 4.64 | +0.51% | 42.1% |

## By season (edge threshold > 3%)

| season | total_bets | roi | hit_rate | max_drawdown | avg_clv | pct_positive_clv |
|---|---|---|---|---|---|---|
| 2021/22 | 631 | -7.95% | 44.1% | 1.86 | +0.67% | 42.5% |
| 2022/23 | 608 | -3.61% | 47.0% | 1.75 | +0.86% | 43.3% |
| 2023/24 | 582 | -9.41% | 41.6% | 2.75 | -0.03% | 40.4% |

## By market (edge threshold > 3%)

| market | total_bets | roi | hit_rate | max_drawdown | avg_clv | pct_positive_clv |
|---|---|---|---|---|---|---|
| h2h | 955 | -9.07% | 37.0% | 2.79 | +0.84% | 43.8% |
| totals | 866 | -5.00% | 52.3% | 2.30 | +0.14% | 40.2% |

## By edge threshold

| edge_threshold_pct | total_bets | roi | hit_rate | max_drawdown | avg_clv | pct_positive_clv |
|---|---|---|---|---|---|---|
| 1% | 2374 | -7.06% | 43.3% | 4.78 | +0.61% | 41.7% |
| 2% | 2068 | -6.97% | 44.1% | 4.71 | +0.60% | 42.2% |
| 3% | 1821 | -6.93% | 44.3% | 4.64 | +0.51% | 42.1% |
| 5% | 1392 | -7.46% | 44.3% | 4.75 | +0.41% | 41.7% |
| 7% | 1060 | -6.37% | 44.6% | 3.72 | +0.37% | 42.3% |
| 10% | 636 | -5.21% | 45.6% | 2.56 | +0.46% | 43.7% |
