"""Deterministic fake API responses so the pipeline can be tested without a key."""
import random
from datetime import date, datetime, timedelta, timezone

rng = random.Random(42)

TEAMS = [
    (101, "Riverton FC"), (102, "Harbour United"), (103, "Oakfield Town"),
    (104, "Kestrel City"), (105, "Milbrook Rovers"), (106, "Ashvale Athletic"),
    (107, "Norcliffe FC"), (108, "Draymoor Wanderers"), (109, "Eastgate SC"),
    (110, "Foxhill United"), (111, "Bramwich Albion"), (112, "Seabury Town"),
]


def _fixture(fid, home, away, when, league_id=39, gh=None, ga=None, status="NS"):
    return {
        "fixture": {"id": fid, "date": when,
                    "status": {"short": status}},
        "league": {"id": league_id, "name": "Premier League"},
        "teams": {"home": {"id": home[0], "name": home[1]},
                  "away": {"id": away[0], "name": away[1]}},
        "goals": {"home": gh, "away": ga},
    }


def fixtures_by_date(date_str):
    out = []
    for i in range(6):
        home, away = TEAMS[2 * i], TEAMS[2 * i + 1]
        when = f"{date_str}T{15 + i % 5}:00:00+00:00"
        out.append(_fixture(9000 + i, home, away, when))
    return out


def fixtures_by_ids(ids):
    out = []
    for fid in ids:
        i = (fid - 9000) % 6
        home, away = TEAMS[2 * i], TEAMS[2 * i + 1]
        gh, ga = rng.choice([(2, 1), (3, 1), (1, 1), (0, 2), (2, 2), (1, 0)])
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        out.append(_fixture(fid, home, away, f"{yesterday}T15:00:00+00:00",
                            gh=gh, ga=ga, status="FT"))
    return out


def team_last_fixtures(team_id, n=6):
    trng = random.Random(team_id)
    out = []
    me = next(t for t in TEAMS if t[0] == team_id)
    for i in range(n):
        opp = trng.choice([t for t in TEAMS if t[0] != team_id])
        gh = trng.choice([0, 1, 1, 2, 2, 3, 4])
        ga = trng.choice([0, 0, 1, 1, 2, 3])
        when = (datetime.now(timezone.utc) - timedelta(days=4 * (i + 1))).isoformat()
        if i % 2 == 0:
            out.append(_fixture(8000 + team_id * 10 + i, me, opp, when,
                                gh=gh, ga=ga, status="FT"))
        else:
            out.append(_fixture(8000 + team_id * 10 + i, opp, me, when,
                                gh=ga, ga=gh, status="FT"))
    return out


def odds_for_fixture(fixture_id):
    orng = random.Random(fixture_id)
    return {
        "OVER_2.5": round(orng.uniform(1.55, 2.10), 2),
        "UNDER_2.5": round(orng.uniform(1.70, 2.30), 2),
        "BTTS_YES": round(orng.uniform(1.55, 2.00), 2),
        "BTTS_NO": round(orng.uniform(1.80, 2.40), 2),
    }
