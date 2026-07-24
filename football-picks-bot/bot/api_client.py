"""Thin client for API-Football (v3.football.api-sports.io).

Free tier: 100 requests/day. The pipeline is budgeted to stay well under.
Set MOCK=1 to run without a key (uses bot/mock_data.py).
"""
import os
import time
import requests

BASE = "https://v3.football.api-sports.io"
MOCK = os.environ.get("MOCK") == "1"


class ApiClient:
    def __init__(self):
        self.requests_made = 0
        if MOCK:
            from bot import mock_data
            self.mock = mock_data
            return
        key = os.environ.get("APIFOOTBALL_KEY")
        if not key:
            raise SystemExit("Set APIFOOTBALL_KEY env var (or MOCK=1 for a dry run).")
        self.headers = {"x-apisports-key": key}

    def _get(self, path, params):
        self.requests_made += 1
        for attempt in range(3):
            r = requests.get(f"{BASE}/{path}", headers=self.headers,
                             params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            body = r.json()
            if body.get("errors"):
                raise RuntimeError(f"API error on /{path}: {body['errors']}")
            return body["response"]
        raise RuntimeError("Rate limited repeatedly")

    def fixtures_by_date(self, date_str):
        if MOCK:
            return self.mock.fixtures_by_date(date_str)
        return self._get("fixtures", {"date": date_str})

    def fixtures_by_ids(self, ids):
        """Settle results: up to 20 fixture ids per request."""
        if MOCK:
            return self.mock.fixtures_by_ids(ids)
        out = []
        for i in range(0, len(ids), 20):
            chunk = "-".join(str(x) for x in ids[i:i + 20])
            out += self._get("fixtures", {"ids": chunk})
        return out

    def team_last_fixtures(self, team_id, n=6):
        if MOCK:
            return self.mock.team_last_fixtures(team_id, n)
        return self._get("fixtures", {"team": team_id, "last": n, "status": "FT"})

    def odds_for_fixture(self, fixture_id):
        """Returns {market: best_decimal_odds} for our four markets."""
        if MOCK:
            return self.mock.odds_for_fixture(fixture_id)
        resp = self._get("odds", {"fixture": fixture_id})
        best = {}
        for entry in resp:
            for bm in entry.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    for v in bet.get("values", []):
                        market = _map_market(bet["name"], str(v["value"]))
                        if market:
                            odd = float(v["odd"])
                            if odd > best.get(market, 0):
                                best[market] = odd
        return best


def _map_market(bet_name, value):
    bet = bet_name.lower()
    val = value.lower()
    if "over/under" in bet or bet == "goals over/under":
        if val == "over 2.5":
            return "OVER_2.5"
        if val == "under 2.5":
            return "UNDER_2.5"
    if "both teams" in bet or "btts" in bet:
        if val == "yes":
            return "BTTS_YES"
        if val == "no":
            return "BTTS_NO"
    return None
