# ev-finder

A CLI that identifies positive expected value (+EV) bets on football (soccer)
match markets: it fetches bookmaker odds, models match outcomes with a
Poisson goals model, strips the bookmaker's vig, and flags bets where the
model's edge over the market exceeds a threshold.

**Status:** data pipeline phase. `fetch-odds` is implemented and tested;
`update-ratings`, `find-value`, `log-bet`, and `report` are stubbed pending
the Poisson model.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync
cp .env.example .env
```

Edit `.env` and set `ODDS_API_KEY` to a free key from
[the-odds-api.com](https://the-odds-api.com/) (free tier: 500 requests/month).

## Example command

```bash
uv run ev-finder fetch-odds
```

Fetches EPL odds for the next 7 days (1X2 and over/under 2.5 markets) and
stores the raw response plus normalized rows in `data/odds.db`. This costs
**1 request** against your monthly quota per run.

## Development

```bash
make test     # run pytest
make lint     # ruff check
make format   # ruff format
make fetch    # uv run ev-finder fetch-odds
make clean    # remove caches and local db
```
