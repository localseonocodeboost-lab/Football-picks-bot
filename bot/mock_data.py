"""Deterministic fake API responses so the pipeline can be tested without a key.

Models the free-tier-friendly design: fixtures_by_date returns NS matches for
today and finished (FT) matches for past dates, so team form can be built
purely from date queries.
"""
import random
from datetime import date, datetime, timedelta, timezone

TEAMS = [
    (101, "Riverton FC"), (102, "Harbour United"), (103, "Oakfield Town"),
    (104, "Kestrel City"), (105, "Milbrook Rovers"), (106, "Ashvale Athletic"),
    (107, "Norcliffe FC"), (108, "Draymoor Wanderers"), (109, "Eastgate SC"),
    (110, "Foxhill United"), (111, "Bramwich Albion"), (112, "Seabury Town"),
]


def _fixture(fid, home, away, when, gh=None, ga=None, status="NS", league_id=39):
    return {
        "fixture": {"id": fid, "date": when, "status": {"short": status}},
        "league": {"id": league_id, "name": "Premier League", "season": 2026},
        "teams": {"home": {"id": home[0], "name": home[1]},
                  "away": {"id": away[0], "name": away[1]}},
        "goals": {"home": gh, "away": ga},
    }


def fixtures_by_date(date_str):
    """Today (== system today) → 6 NS matches. Past dates → finished matches."""
    today = date.today().isoformat()
    if date_str == today:
        out = []
        for i in range(6):
            home, away = TEAMS[2 * i], TEAMS[2 * i + 1]
            out.append(_fixture(90000 + i, home, away,
                                f"{date_str}T15:00:00+00:00"))
        return out
    # Past date: deterministic set of finished results involving many teams.
    rng = random.Random(date_str)
    out = []
    shuffled = TEAMS[:]
    rng.shuffle(shuffled)
    for i in range(0, len(shuffled) - 1, 2):
        home, away = shuffled[i], shuffled[i + 1]
        gh = rng.choice([0, 1, 1, 2, 2, 3, 4])
        ga = rng.choice([0, 0, 1, 1, 2, 3])
        fid = 70000 + abs(hash(date_str)) % 1000 + i
        out.append(_fixture(fid, home, away, f"{date_str}T15:00:00+00:00",
                            gh=gh, ga=ga, status="FT"))
    return out


def odds_for_fixture(fixture_id):
    orng = random.Random(fixture_id)
    return {
        "OVER_2.5": round(orng.uniform(1.55, 2.10), 2),
        "UNDER_2.5": round(orng.uniform(1.70, 2.30), 2),
        "BTTS_YES": round(orng.uniform(1.55, 2.00), 2),
        "BTTS_NO": round(orng.uniform(1.80, 2.40), 2),
    }
