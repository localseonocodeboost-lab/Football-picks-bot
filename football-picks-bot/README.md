# Football Picks Bot

Your own version of aibettingbot.co.uk: a daily bot that models football
fixtures, picks up to 5 value bets in the Over/Under 2.5 Goals and BTTS
markets, tracks every result, and publishes a dashboard.

## How it works

1. **Fetch** today's fixtures (API-Football free tier, ~40 of the 100 daily requests).
2. **Model** each fixture with a Poisson goals model: each team's attack/defence
   rates from its last 6 matches → expected goals → P(Over 2.5) and P(BTTS).
3. **Compare** model probability vs bookmaker implied probability; only fixtures
   where the model beats the price by ≥4% qualify. Top 5 by edge become picks.
4. **Settle** yesterday's picks against final scores; track win rate, P/L, ROI.
5. **Publish** `docs/index.html` — win rate, record, monthly form, full results list.

## Setup (one-time, ~10 minutes)

### 1. API key
- Sign up free at https://dashboard.api-football.com (100 requests/day tier).
- Copy your API key.

### 2. GitHub repo
- Create a new **private** GitHub repo and push this folder to it.
- Repo → Settings → Secrets and variables → Actions → **New repository secret**:
  name `APIFOOTBALL_KEY`, value = your key.
- Repo → Settings → Pages → Source: **Deploy from a branch**, branch `main`,
  folder `/docs`. Your dashboard will be at
  `https://<username>.github.io/<repo>/`.

### 3. Done
The workflow runs every day at 08:00 UTC (edit the cron in
`.github/workflows/daily.yml` to change). Trigger it manually anytime from the
Actions tab → "Daily picks" → Run workflow.

## Run locally

```bash
pip install -r requirements.txt

# dry run with fake data (no key needed):
MOCK=1 python run.py          # PowerShell: $env:MOCK="1"; python run.py

# real run:
APIFOOTBALL_KEY=yourkey python run.py
```

Then open `docs/index.html`.

## Tuning

All knobs are at the top of `bot/pipeline.py`:

| Setting | Default | Meaning |
|---|---|---|
| `MIN_PROB` | 0.55 | model probability floor for a pick |
| `MIN_EDGE` | 0.04 | model must beat the odds' implied prob by this |
| `MIN_ODDS` | 1.30 | skip prices shorter than this |
| `MAX_PICKS` | 5 | picks per day |
| `MAX_CANDIDATES` | 12 | fixtures analysed daily (request budget) |
| `LEAGUES` | 21 leagues | which competitions to model |

## Honest expectations

The original site's 75% win rate comes from betting short odds — at average
odds of ~1.5 you need 67% just to break even. A simple Poisson model finds
real signal in goals markets, but bookmaker margins are hard to beat long-term.
Track your own results for a few months before trusting the model with
meaningful stakes — that's what the dashboard is for.

**This is for entertainment. Never bet money you can't afford to lose.
18+ · BeGambleAware.org · GamCare 0808 8020 133.**
