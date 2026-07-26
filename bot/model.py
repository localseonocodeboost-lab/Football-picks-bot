"""Poisson goal model — the statistical core.

Estimates expected goals for each side from recent form, then converts
to probabilities for the two markets the original site trades:
Over/Under 2.5 Goals and Both Teams To Score.
"""
import math

LEAGUE_AVG_GOALS = 1.35   # avg goals per team per match (global fallback)
HOME_ADVANTAGE = 1.10
AWAY_PENALTY = 0.92
XG_CAP = 3.2              # sanity cap on a single team's expected goals


def team_rates(recent_matches, team_id):
    """Avg goals scored/conceded per game from a list of recent fixtures."""
    scored, conceded, n = 0, 0, 0
    for m in recent_matches:
        gh, ga = m["goals"]["home"], m["goals"]["away"]
        if gh is None or ga is None:
            continue
        if m["teams"]["home"]["id"] == team_id:
            scored += gh
            conceded += ga
        else:
            scored += ga
            conceded += gh
        n += 1
    if n == 0:
        return None
    return {"scored": scored / n, "conceded": conceded / n, "games": n}


def expected_goals(home, away):
    """Expected goals (lambda) for home and away sides.

    attack * opponent-defence, normalised by league average.
    """
    lam_home = home["scored"] * away["conceded"] / LEAGUE_AVG_GOALS * HOME_ADVANTAGE
    lam_away = away["scored"] * home["conceded"] / LEAGUE_AVG_GOALS * AWAY_PENALTY
    return min(max(lam_home, 0.15), XG_CAP), min(max(lam_away, 0.15), XG_CAP)


def _poisson_cdf(k, lam):
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def market_probs(lam_home, lam_away):
    """Probabilities for the markets we trade.

    Sum of independent Poissons is Poisson(lam_h + lam_a).
    """
    total = lam_home + lam_away
    p_over25 = 1 - _poisson_cdf(2, total)
    p_btts = (1 - math.exp(-lam_home)) * (1 - math.exp(-lam_away))
    return {
        "OVER_2.5": p_over25,
        "UNDER_2.5": 1 - p_over25,
        "BTTS_YES": p_btts,
        "BTTS_NO": 1 - p_btts,
    }


def implied_prob(decimal_odds):
    return 1.0 / decimal_odds if decimal_odds and decimal_odds > 1 else None


def evaluate_pick(market, score_home, score_away):
    """Settle a market given the final score. Returns True/False."""
    total = score_home + score_away
    both = score_home > 0 and score_away > 0
    return {
        "OVER_2.5": total > 2.5,
        "UNDER_2.5": total < 2.5,
        "BTTS_YES": both,
        "BTTS_NO": not both,
    }[market]


MARKET_LABELS = {
    "OVER_2.5": "Over 2.5 Goals",
    "UNDER_2.5": "Under 2.5 Goals",
    "BTTS_YES": "Both Teams To Score — Yes",
    "BTTS_NO": "Both Teams To Score — No",
}
