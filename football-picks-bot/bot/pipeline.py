"""Daily pipeline — free-tier friendly, powered by the Predictions endpoint.

Free tier gives only a 3-day date window and blocks historical results, so we
get each team's recent form from /predictions (which embeds last-5 goals
averages), settle yesterday's picks from fixtures-by-date (in-window), and read
pre-match odds. Same Poisson model, different form source.

Budget (100 req/day): 1 today + 2 settle-date + MAX_CANDIDATES*(1 pred + 1 odds)
≈ 31/day.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

from bot.api_client import ApiClient
from bot import model

DATA_FILE = os.path.join("data", "picks.json")
STAKE = 10.0
MAX_CANDIDATES = 14
MAX_PICKS = 5
MIN_PROB = 0.55
MIN_EDGE = 0.04
MIN_ODDS = 1.30
MIN_GAMES = 3

LEAGUES = {
    39: "Premier League", 40: "Championship", 140: "La Liga", 135: "Serie A",
    78: "Bundesliga", 61: "Ligue 1", 88: "Eredivisie", 94: "Primeira Liga",
    203: "Süper Lig", 179: "Scottish Premiership", 71: "Série A (BR)",
    253: "MLS", 98: "J1 League", 292: "K League 1", 113: "Allsvenskan",
    103: "Eliteserien", 106: "Ekstraklasa", 119: "Superliga (DK)",
    2: "Champions League", 3: "Europa League", 848: "Conference League",
}
FINISHED = ("FT", "AET", "PEN")
VOIDED = ("CANC", "PST", "ABD", "AWD", "WO")


def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"picks": []}


def save_db(db):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=1)


def settle_pending(api, db):
    pending = [p for p in db["picks"] if p["status"] == "pending"]
    if not pending:
        return 0
    pool = []
    for d in (1, 0):  # yesterday, today — both inside the free 3-day window
        ds = (date.today() - timedelta(days=d)).isoformat()
        try:
            pool += api.fixtures_by_date(ds)
        except Exception as e:
            print(f"  (settle skip {ds}: {e})")
    by_id = {m["fixture"]["id"]: m for m in pool}
    settled = 0
    for p in pending:
        m = by_id.get(p["fixture_id"])
        if not m:
            continue
        status = m["fixture"]["status"]["short"]
        if status in FINISHED:
            gh, ga = m["goals"]["home"], m["goals"]["away"]
            won = model.evaluate_pick(p["market"], gh, ga)
            p["status"] = "won" if won else "lost"
            p["score"] = f"{gh}-{ga}"
            p["profit"] = round(STAKE * (p["odds"] - 1), 2) if won else -STAKE
            settled += 1
        elif status in VOIDED:
            p["status"], p["profit"] = "void", 0.0
            settled += 1
    return settled


def rates_from_pred(pred, side):
    """Build {scored, conceded, games} from a team's last-5 in a prediction."""
    try:
        l5 = pred["teams"][side]["last_5"]
        g = l5["goals"]
        scored = float(g["for"]["average"])
        conceded = float(g["against"]["average"])
        games = int(l5.get("played") or 5)
        return {"scored": scored, "conceded": conceded, "games": games}
    except (KeyError, TypeError, ValueError):
        return None


def generate_picks(api, db):
    today = date.today().isoformat()
    if any(p["date"] == today for p in db["picks"]):
        print("Picks already generated today — skipping generation.")
        return []

    fixtures = api.fixtures_by_date(today)
    candidates = [f for f in fixtures
                  if f["league"]["id"] in LEAGUES
                  and f["fixture"]["status"]["short"] == "NS"]
    priority = {lid: i for i, lid in enumerate(LEAGUES)}
    candidates.sort(key=lambda f: priority[f["league"]["id"]])
    candidates = candidates[:MAX_CANDIDATES]
    print(f"{len(fixtures)} fixtures today, {len(candidates)} in tracked leagues.")

    scored, with_pred, with_odds = [], 0, 0
    for f in candidates:
        pred = api.predictions_for_fixture(f["fixture"]["id"])
        if not pred:
            continue
        home = rates_from_pred(pred, "home")
        away = rates_from_pred(pred, "away")
        if not home or not away or home["games"] < MIN_GAMES or away["games"] < MIN_GAMES:
            continue
        with_pred += 1
        lam_h, lam_a = model.expected_goals(home, away)
        probs = model.market_probs(lam_h, lam_a)
        odds = api.odds_for_fixture(f["fixture"]["id"])
        if odds:
            with_odds += 1
        for market, p in probs.items():
            if p < MIN_PROB:
                continue
            o = odds.get(market)
            if not o or o < MIN_ODDS:
                continue
            edge = p - model.implied_prob(o)
            if edge < MIN_EDGE:
                continue
            scored.append({
                "fixture_id": f["fixture"]["id"], "date": today,
                "kickoff": f["fixture"]["date"], "league": f["league"]["name"],
                "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
                "market": market, "market_label": model.MARKET_LABELS[market],
                "odds": o, "model_prob": round(p, 3), "edge": round(edge, 3),
                "xg": [round(lam_h, 2), round(lam_a, 2)],
                "reasoning": _reasoning(f, home, away, lam_h, lam_a, market, p),
                "status": "pending", "profit": None,
            })

    print(f"Form via predictions: {with_pred}; odds: {with_odds}; of {len(candidates)} candidates.")
    scored.sort(key=lambda s: s["edge"], reverse=True)
    picks, used = [], set()
    for s in scored:
        if s["fixture_id"] in used:
            continue
        picks.append(s)
        used.add(s["fixture_id"])
        if len(picks) == MAX_PICKS:
            break
    db["picks"] += picks
    return picks


def _reasoning(f, home, away, lam_h, lam_a, market, p):
    h, a = f["teams"]["home"]["name"], f["teams"]["away"]["name"]
    return (f"{h} averaging {home['scored']:.1f} scored / {home['conceded']:.1f} "
            f"conceded over last {home['games']}; {a} {away['scored']:.1f} / "
            f"{away['conceded']:.1f}. Model projects {lam_h:.1f}–{lam_a:.1f} xG. "
            f"{model.MARKET_LABELS[market]} lands in {p:.0%} of simulations.")


def run():
    api = ApiClient()
    db = load_db()
    try:
        settled = settle_pending(api, db)
        print(f"Settled {settled} pick(s).")
        picks = generate_picks(api, db)
        for p in picks:
            print(f"  PICK: {p['home']} v {p['away']} — {p['market_label']} "
                  f"@ {p['odds']} (model {p['model_prob']:.0%}, edge +{p['edge']:.1%})")
        if not picks:
            print("No value picks today (normal — the filter is deliberately picky).")
    except Exception as e:
        print(f"Run hit an error but will still publish the dashboard: {e}")
    db["updated"] = datetime.now(timezone.utc).isoformat()
    save_db(db)
    print(f"API requests used: {api.requests_made}")
    from bot.dashboard import build
    build(db)


if __name__ == "__main__":
    run()
