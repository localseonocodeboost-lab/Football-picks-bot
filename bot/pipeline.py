"""Daily pipeline — free-tier friendly (form + settlement from date queries)."""
import json
import os
from datetime import date, datetime, timedelta, timezone

from bot.api_client import ApiClient
from bot import model

DATA_FILE = os.path.join("data", "picks.json")
STAKE = 10.0
FORM_WINDOW_DAYS = 35
FORM_MATCHES = 8
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


def gather_pool(api):
    today_fixtures, pool = [], []
    for d in range(0, FORM_WINDOW_DAYS + 1):
        ds = (date.today() - timedelta(days=d)).isoformat()
        try:
            fx = api.fixtures_by_date(ds)
        except Exception as e:
            print(f"  (skipped {ds}: {e})")
            continue
        if d == 0:
            today_fixtures = fx
        pool += fx
    return date.today().isoformat(), today_fixtures, pool


def team_matches(pool, team_id):
    ms = [m for m in pool
          if m["fixture"]["status"]["short"] in FINISHED
          and team_id in (m["teams"]["home"]["id"], m["teams"]["away"]["id"])]
    ms.sort(key=lambda m: m["fixture"]["date"], reverse=True)
    return ms[:FORM_MATCHES]


def settle_pending(pool, db):
    by_id = {m["fixture"]["id"]: m for m in pool}
    settled = 0
    for p in db["picks"]:
        if p["status"] != "pending":
            continue
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


def generate_picks(api, db, today_str, today_fixtures, pool):
    if any(p["date"] == today_str for p in db["picks"]):
        print("Picks already generated today — skipping generation.")
        return []
    candidates = [f for f in today_fixtures
                  if f["league"]["id"] in LEAGUES
                  and f["fixture"]["status"]["short"] == "NS"]
    priority = {lid: i for i, lid in enumerate(LEAGUES)}
    candidates.sort(key=lambda f: priority[f["league"]["id"]])
    candidates = candidates[:MAX_CANDIDATES]
    print(f"{len(today_fixtures)} fixtures today, {len(candidates)} in tracked leagues.")

    scored, with_odds = [], 0
    for f in candidates:
        hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
        home = model.team_rates(team_matches(pool, hid), hid)
        away = model.team_rates(team_matches(pool, aid), aid)
        if not home or not away or home["games"] < MIN_GAMES or away["games"] < MIN_GAMES:
            continue
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
                "fixture_id": f["fixture"]["id"], "date": today_str,
                "kickoff": f["fixture"]["date"], "league": f["league"]["name"],
                "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
                "market": market, "market_label": model.MARKET_LABELS[market],
                "odds": o, "model_prob": round(p, 3), "edge": round(edge, 3),
                "xg": [round(lam_h, 2), round(lam_a, 2)],
                "reasoning": _reasoning(f, home, away, lam_h, lam_a, market, p),
                "status": "pending", "profit": None,
            })

    print(f"Odds available for {with_odds}/{len(candidates)} candidates.")
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
            f"{away['conceded']:.1f}. Model projects {lam_h:.1f}\u2013{lam_a:.1f} xG. "
            f"{model.MARKET_LABELS[market]} lands in {p:.0%} of simulations.")


def run():
    api = ApiClient()
    db = load_db()
    try:
        today_str, today_fixtures, pool = gather_pool(api)
        print(f"Pool: {len(pool)} fixtures across {FORM_WINDOW_DAYS} days.")
        settled = settle_pending(pool, db)
        print(f"Settled {settled} pick(s).")
        picks = generate_picks(api, db, today_str, today_fixtures, pool)
        for p in picks:
            print(f"  PICK: {p['home']} v {p['away']} \u2014 {p['market_label']} "
                  f"@ {p['odds']} (model {p['model_prob']:.0%}, edge +{p['edge']:.1%})")
        if not picks:
            print("No value picks today (normal).")
    except Exception as e:
        print(f"Run hit an error but will still publish the dashboard: {e}")
    db["updated"] = datetime.now(timezone.utc).isoformat()
    save_db(db)
    print(f"API requests used: {api.requests_made}")
    from bot.dashboard import build
    build(db)


if __name__ == "__main__":
    run()
