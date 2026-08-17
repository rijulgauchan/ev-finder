# ev-finder

I built a Dixon-Coles Poisson goals model for English Premier League matches and backtested it walk-forward, with a strict no-leak guarantee, against three seasons of the odds that would actually have been available when each bet was made. It loses money: -6.93% ROI on 1,821 flagged bets at a 3% edge threshold. That result holds across every edge threshold I tried and is worse, not better, on over/under 2.5 goals — the market where a Poisson model has the clearest theoretical case for an edge. I also computed closing-line value (CLV) for every flagged bet, as a check on whether the model shows any skill signal independent of these specific outcomes: average CLV is marginally positive (+0.51%), but only 42% of individual bets had positive CLV, so this isn't clean evidence of skill either. The pipeline — live odds ingestion, historical data, the model, the backtest harness, and CLV analysis — works end to end and is documented below. The finding is that a naive implementation of a 25+ year old public model doesn't clearly beat the market, which is itself the expected, useful result of doing this properly before risking money on it.

![Cumulative P&L of flagged bets, 2021-08-01 to 2024-05-31](assets/cumulative_pnl.png)

## Motivation

Football betting markets are a reasonable target for a modeling exercise because the underlying event (a match) reduces to a small number of countable outcomes (goals), there's a long public track record of models that work reasonably well (Dixon-Coles 1997 among them), and there's an unusually clean way to check your work: bookmaker odds, and specifically how those odds move between when a bet could be placed and when the match kicks off.

I picked Poisson/Dixon-Coles specifically because goals in a match are well-approximated by a low-count Poisson process, and Dixon-Coles' contribution — a small correlation correction (`rho`) on the low-scoring cells (0-0, 1-0, 0-1, 1-1) — fixes the one place a naive independent-Poisson model is known to misfire (plain independent Poisson underestimates how often low-scoring games end in a draw). It's a well-understood, well-published baseline, not something exotic, which makes it a fair test: if a clean implementation of a known-good model can't clear the bar, that's informative in itself.

I backtested before wiring anything into live betting recommendations on purpose. It's easy to write a model that looks good because it was accidentally trained on data from the future, evaluated against a price that wasn't actually obtainable when the bet would have been placed, or graded by a metric that doesn't correspond to money won or lost. The only way I trust a result enough to act on it is to prove, mechanically, that the evaluation couldn't have cheated in any of those ways — which is what the walk-forward structure, the no-leak tests, and the pre-closing/closing odds split below are for.

## Method

**Data.** Live odds come from [The Odds API](https://the-odds-api.com/) (free tier, 500 requests/month), stored raw with timestamps in SQLite. Historical results and odds come from [football-data.co.uk](https://www.football-data.co.uk/) — 6 EPL seasons (2019/20 through 2024/25, 2,280 matches). Critically, football-data.co.uk provides **two** odds snapshots per bookmaker per market: a pre-closing snapshot (an earlier price, despite the plain column name) and a true closing snapshot (an explicit "C"-suffixed column, e.g. `B365CH`, captured at kickoff) — [documented here](https://www.football-data.co.uk/notes.txt). Both are ingested, for both 1X2 and over/under 2.5. This distinction turned out to matter more than it sounds like it should (see below).

**Model.** Dixon-Coles (1997): each team gets a multiplicative attack strength and defense strength, fit jointly by maximum likelihood via `scipy.optimize`, with a fixed home-advantage multiplier and the `rho` low-score correlation term. Matches are time-weighted by an exponential decay (`xi = 0.0065`/day) so recent form matters more than results from years ago. Attack strengths are normalized to sum to the number of teams for identifiability — an arbitrary but necessary scale choice, since the model's actual predictions are invariant to it. Fitted parameters produce a full scoreline probability grid, which collapses into 1X2, over/under 2.5, and BTTS market probabilities.

**Backtest.** Walk-forward, not train/test split: for every unique matchday from 2021-08-01 onward, the model is refit on all matches *strictly before* that date and used to predict only that day's fixtures, before rolling forward and refitting again. That guarantee is enforced in code, not just by convention: `DixonColesModel.fit(matches, as_of_date)` filters to `date < as_of_date` before anything else touches the data, and [`tests/test_backtest_no_leak.py`](tests/test_backtest_no_leak.py) checks it by feeding the model deliberately poisoned future rows (impossible scorelines, a phantom team) dated on and after the cutoff and asserting the fitted parameters are bit-identical to a fit that never saw those rows at all.

That closes the model-level leak. There's a second, easier-to-miss one: **which odds the bet decision is graded against.** My first pass at this backtest benchmarked every flagged bet against the true *closing* price — the standard-sounding "beat the closing line" framing. That's wrong: the closing price isn't set until kickoff, so a decision graded against it is being graded against information that wouldn't have existed yet at decision time. The fix — and what this backtest actually does — is that every flagged bet, its stake, and its settlement are driven **entirely by the pre-closing price**, the one that would genuinely have been on offer when the model's prediction was made. The true closing price is used for exactly one thing afterward: computing CLV, a diagnostic, never an input back into the decision. [`tests/test_backtest_engine.py`](tests/test_backtest_engine.py) has a dedicated test (`test_decision_is_independent_of_closing_reference_odds`) that corrupts the closing-reference price with implausible and missing values and asserts the flagged bet, its stake, and its P&L don't change at all — only `clv_pct` does.

**Vig removal, staking, and CLV.** Bookmaker odds are converted to fair probabilities with the multiplicative method (implied probabilities normalized to sum to 1) before comparing to the model — otherwise you're partly just measuring the bookmaker's margin, not their forecast. A bet is flagged when `model_prob - market_prob_no_vig` (both computed from the pre-closing price) exceeds an edge threshold (default 3%), sized with fractional Kelly (default quarter-Kelly, i.e. 0.25x the mathematically optimal stake). CLV per bet is `(pre_closing_price / true_closing_price - 1) * 100`: positive means the price taken was more favorable than where the line ended up.

## Findings

Over the walk-forward backtest window (2021-08-01 to 2024-05-31, 3 full seasons), the model lost money on every cut of the data I looked at.

| | |
|---|---|
| Total bets | 1,821 |
| ROI | **-6.93%** |
| Hit rate | 44.3% |
| Max drawdown | 4.64 units |

Split by market, it's worse on 1X2 (-9.07% ROI, 955 bets) than on totals (-5.00% ROI, 866 bets) — notable because over/under 2.5 is exactly where a goals-based Poisson model has the strongest theoretical claim to an edge (it's a direct model of the thing being bet on, rather than a derived comparison of two teams' relative strength). It wasn't better there. It also isn't a threshold artifact: I re-ran the backtest at six edge thresholds from 1% to 10%, and ROI stayed negative throughout, ranging from -5.21% to -7.46% with no threshold anywhere near break-even.

![ROI vs. edge threshold](assets/roi_by_threshold.png)

**CLV.** Across the same 1,821 bets, average CLV is **+0.51%** — the pre-closing prices taken were, on average, very slightly better than where those lines closed. But only **42.1%** of individual bets had positive CLV. Those two numbers together are a genuinely mixed signal, not a hidden win dressed up as a loss: a minority of bets moved favorably, apparently by more than the majority moved unfavorably, which is enough to pull the mean above zero without it representing a repeatable edge. CLV was positive on average in 2021/22 (+0.67%) and 2022/23 (+0.86%) but roughly flat in 2023/24 (-0.03%), and slightly higher on 1X2 (+0.84%) than totals (+0.14%) — the opposite ranking from ROI, where totals was the *less bad* market. Full breakdowns — by season, by market, by edge threshold — are in [RESULTS.md](RESULTS.md), which contains only the measured numbers; everything evaluative is here.

My honest read: this is roughly what a naive model should look like against a reasonably efficient market, not a bug to chase. Bet365's pre-closing price already incorporates recent results, home advantage, and goal-scoring correlation — everything my model uses — plus everything it doesn't (injuries, lineup news, weather, money flow). Beating it outright with a Poisson model and public results data alone would be the surprising outcome. The CLV numbers don't rescue that conclusion: they're too weak and too inconsistent (barely positive on average, negative for most individual bets) to read as evidence of real skill.

**Is Bet365 specifically the problem?** No. I re-ran the identical backtest against Pinnacle (the other benchmark-sharp book) and the market average, using each book's own pre-closing price to drive the decision and its own closing price for CLV — same methodology, different bookmaker. Every book, every market, was negative: Pinnacle's h2h was the least bad at -6.58%, still solidly unprofitable, and in the same range as the season-to-season and threshold-to-threshold noise already seen against Bet365. The market average didn't do any better. Full table in [RESULTS.md](RESULTS.md). That closes off the most obvious "maybe it's just this one sharp book" explanation — the negative result isn't a Bet365 artifact, and the remaining open question is whether specific markets or situations, not the aggregate, hide a real edge.

## Next steps

- ~~Multi-book comparison.~~ **Done, closed.** Bet365, Pinnacle, and the market average all show negative ROI across both markets (see Findings above and [RESULTS.md](RESULTS.md)) — the negative result isn't specific to one sharp book.
- **Over/under 2.5, specifically.** It underperformed 1X2 here, which is itself worth understanding rather than shrugging off — is the Poisson goal-count assumption too rigid, is `rho` mis-calibrated for the totals market, or is there a staking/threshold interaction I haven't isolated?
- **The CLV/ROI split by market.** 1X2 had worse ROI but better average CLV than totals — worth digging into whether that's noise or a real difference in how those two markets move between pre-closing and closing.
- **`find-value` stays unwired.** Given these results, wiring the model into live betting recommendations isn't justified yet. That's a deliberate scope decision, not a missing feature.

## Repo structure

```
src/ev_finder/
├── odds/          # live odds ingestion (The Odds API) -> SQLite
├── historical/     # historical results + pre-closing/closing odds (football-data.co.uk) -> SQLite
├── model/          # Dixon-Coles Poisson goals model (dixon_coles.py)
├── backtest/       # walk-forward backtest engine: pre-closing decision, closing-only CLV, Kelly staking
├── ev/             # vig removal
├── tracking/        # (unbuilt) live bet logging, CLV/ROI tracking
├── cli.py           # Typer CLI: fetch-odds, ingest-historical, backtest, ...
├── db.py            # SQLite schema
└── config.py         # .env / settings loading

scripts/
├── generate_report.py       # regenerates RESULTS.md and the two charts above
└── multibook_experiment.py  # multi-book comparison (Bet365/Pinnacle/average), appends to RESULTS.md

tests/                # pytest: vig math, Dixon-Coles fit/tau, Kelly staking, no-leak guarantees
assets/               # charts embedded in this README
RESULTS.md            # full numeric breakdown (by season, market, threshold, book) -- measured only
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync
cp .env.example .env   # set ODDS_API_KEY (free key from the-odds-api.com)
```

```bash
uv run ev-finder fetch-odds                                    # live EPL odds -> SQLite
uv run ev-finder ingest-historical --seasons 2019-2024          # historical results + odds -> SQLite
uv run ev-finder backtest --start 2021-08-01 --end 2024-05-31   # walk-forward backtest + CLV
```

`make test` / `make lint` / `make format` run pytest / ruff check / ruff format.

To reproduce everything in this README and in [RESULTS.md](RESULTS.md) from scratch:

```bash
uv run ev-finder ingest-historical --seasons 2019-2024
uv run python scripts/generate_report.py
uv run python scripts/multibook_experiment.py   # multi-book comparison section
```

The report script re-runs the backtest at the default 3% edge threshold plus a 1/2/3/5/7/10% sweep (~10-15 minutes total; it refits the model once per matchday) and regenerates `RESULTS.md`, `assets/cumulative_pnl.png`, and `assets/roi_by_threshold.png` from whatever's in the database at the end.
