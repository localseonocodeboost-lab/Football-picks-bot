"""Daily pipeline: settle yesterday's picks, generate today's picks.

Budget (free tier = 100 req/day): 1 fixtures call + 1-2 settlement calls
+ (2 stats + 1 odds) per candidate fixture, capped at MAX_CANDIDATES.
"""
import json
import os
from datetime import date, datetime, timezone

from bot.api_client import ApiClient
from bot import model

DATA_FILE = os.path.join("data", "picks.json")
STAKE = 10.0            # units per pick (dashboard math only — not real money)
MAX_CANDIDATES = 12     # fixtures to fully analyse per day
MAX_PICKS = 5
MIN_PROB = 0.55         # model probability floor
MIN_EDGE = 0.04         # model prob must beat implied prob by this much
MIN_ODDS = 1.30         # skip anything shorter (no value at silly prices)
MIN_GAMES = 4           # each team needs at least this many recent results

# Leagues worth modelling (API-Football league ids). Add/remove freely.
LEAGUES = {
    39: "Premier League", 40: "Championship", 140: "La Liga", 135: "Serie A",
    78: "Bundesliga", 61: "Ligue 1", 88: "Eredivisie", 94: "Primeira Liga",
    203: "Süper Lig", 179: "Scottish Premiership", 71: "Série A (BR)",
    253: "MLS", 98: "J1 League", 292: "K League 1", 113: "Allsvenskan",
    103: "Eliteserien", 106: "Ekstraklasa", 119: "Superliga (DK)",
    2: "Champions League", 3: "Europa League", 848: "Conference League",
}


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
    results = api.fixtures_by_ids([p["fixture_id"] for p in pending])
    by_id = {r["fixture"]["id"]: r for r in results}
    settled = 0
    for p in pending:
        r = by_id.get(p["fixture_id"])
        if not r:
            continue
        status = r["fixture"]["status"]["short"]
        if status in ("FT", "AET", "PEN"):
            gh, ga = r["goals"]["home"], r["goals"]["away"]
            won = model.evaluate_pick(p["market"], gh, ga)
            p["status"] = "won" if won else "lost"
            p["score"] = f"{gh}-{ga}"
            p["profit"] = round(STAKE * (p["odds"] - 1), 2) if won else -STAKE
            settled += 1
        elif status in ("CANC", "PST", "ABD", "AWD", "WO"):
            p["status"] = "void"
            p["profit"] = 0.0
            settled += 1
    return settled


def generate_picks(api, db):
    today = date.today().isoformat()
    if any(p["date"] == today for p in db["picks"]):
        print("Picks already generated today — skipping.")
        return []

    fixtures = api.fixtures_by_date(today)
    candidates = [
        f for f in fixtures
        if f["league"]["id"] in LEAGUES and f["fixture"]["status"]["short"] == "NS"
    ]
    # Prefer bigger leagues (dict order above is roughly priority order)
    priority = {lid: i for i, lid in enumerate(LEAGUES)}
    candidates.sort(key=lambda f: priority[f["league"]["id"]])
    candidates = candidates[:MAX_CANDIDATES]
    print(f"{len(fixtures)} fixtures today, analysing {len(candidates)}.")

    scored = []
    for f in candidates:
        hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
        home = model.team_rates(api.team_last_fixtures(hid), hid)
        away = model.team_rates(api.team_last_fixtures(aid), aid)
        if not home or not away or home["games"] < MIN_GAMES or away["games"] < MIN_GAMES:
            continue
        lam_h, lam_a = model.expected_goals(home, away)
        probs = model.market_probs(lam_h, lam_a)
        odds = api.odds_for_fixture(f["fixture"]["id"])
        for market, p in probs.items():
            o = odds.get(market)
            if not o or o < MIN_ODDS or p < MIN_PROB:
                continue
            edge = p - model.implied_prob(o)
            if edge < MIN_EDGE:
                continue
            scored.append({
                "fixture_id": f["fixture"]["id"],
                "date": today,
                "kickoff": f["fixture"]["date"],
                "league": f["league"]["name"],
                "home": f["teams"]["home"]["name"],
                "away": f["teams"]["away"]["name"],
                "market": market,
                "market_label": model.MARKET_LABELS[market],
                "odds": o,
                "model_prob": round(p, 3),
                "edge": round(edge, 3),
                "xg": [round(lam_h, 2), round(lam_a, 2)],
                "reasoning": _reasoning(f, home, away, lam_h, lam_a, market, p),
                "status": "pending",
                "profit": None,
            })

    # One pick per fixture, best edge first
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
    base = (f"{h} averaging {home['scored']:.1f} scored / {home['conceded']:.1f} "
            f"conceded over last {home['games']}; {a} {away['scored']:.1f} / "
            f"{away['conceded']:.1f}. Model projects {lam_h:.1f}–{lam_a:.1f} xG.")
    return f"{base} {model.MARKET_LABELS[market]} lands in {p:.0%} of simulations."


def run():
    api = ApiClient()
    db = load_db()
    settled = settle_pending(api, db)
    print(f"Settled {settled} pick(s).")
    picks = generate_picks(api, db)
    for p in picks:
        print(f"  PICK: {p['home']} v {p['away']} — {p['market_label']} "
              f"@ {p['odds']} (model {p['model_prob']:.0%}, edge +{p['edge']:.1%})")
    if not picks:
        print("No value picks today — that's normal; the filter is meant to be picky.")
    db["updated"] = datetime.now(timezone.utc).isoformat()
    save_db(db)
    print(f"API requests used: {api.requests_made}")
    from bot.dashboard import build
    build(db)


if __name__ == "__main__":
    run()
