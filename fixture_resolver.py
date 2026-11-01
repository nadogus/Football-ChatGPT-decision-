"""Fail-closed fixture/provider ID resolution.

Resolves provider event IDs from team names + kickoff context.
Never invents an ID. Ambiguous/weak matches remain unresolved evidence gaps.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
import re

from data_adapters import ESPNLineupClient, FotMobLineupClient, FlashscoreClient, PinnaclePrematchClient, OddsHarvesterClient, _json


RESOLVER_VERSION = "FIXTURE_RESOLVER_V1.0"


def _norm(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(fc|cf|afc|sc|ac|club|football|futbol|soccer)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _team_score(a: str | None, b: str | None) -> float:
    aa, bb = _norm(a), _norm(b)
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    return SequenceMatcher(None, aa, bb).ratio()


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        x = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if x.tzinfo is None:
            x = x.replace(tzinfo=timezone.utc)
        return x.astimezone(timezone.utc)
    except Exception:
        return None


def _kickoff_score(target: str | None, candidate: str | None, tolerance_minutes: int = 180) -> float:
    a, b = _dt(target), _dt(candidate)
    if not a or not b:
        return 0.5
    delta = abs((a - b).total_seconds()) / 60.0
    if delta > tolerance_minutes:
        return 0.0
    return max(0.0, 1.0 - delta / tolerance_minutes)


def fixture_score(match: dict[str, Any], home: str | None, away: str | None, kickoff: str | None) -> float:
    h = _team_score(match.get("home"), home)
    a = _team_score(match.get("away"), away)
    k = _kickoff_score(match.get("kickoff"), kickoff)
    return round(0.425 * h + 0.425 * a + 0.15 * k, 6)


def _walk_events(x: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(x, dict):
        # Common event shapes across providers.
        home = x.get("home")
        away = x.get("away")
        if isinstance(home, dict):
            home = home.get("name") or home.get("shortName")
        if isinstance(away, dict):
            away = away.get("name") or away.get("shortName")
        if not home or not away:
            comps = x.get("competitors")
            if isinstance(comps, list):
                for c in comps:
                    if not isinstance(c, dict):
                        continue
                    team = c.get("team") if isinstance(c.get("team"), dict) else c
                    name = team.get("displayName") or team.get("name") or team.get("shortDisplayName")
                    side = c.get("homeAway") or c.get("alignment")
                    if side == "home":
                        home = name
                    elif side == "away":
                        away = name
        if home and away:
            out.append({
                "id": x.get("id") or x.get("eventId") or x.get("matchId") or x.get("matchupId"),
                "home": home,
                "away": away,
                "kickoff": x.get("date") or x.get("startTime") or x.get("start") or x.get("utcTime"),
                "raw": x,
            })
        for v in x.values():
            out.extend(_walk_events(v))
    elif isinstance(x, list):
        for v in x:
            out.extend(_walk_events(v))
    return out


def best_fixture(match: dict[str, Any], candidates: list[dict[str, Any]], threshold: float = 0.86, margin: float = 0.06) -> dict[str, Any]:
    scored = []
    for c in candidates:
        if not c.get("id"):
            continue
        s = fixture_score(match, c.get("home"), c.get("away"), c.get("kickoff"))
        scored.append((s, c))
    scored.sort(key=lambda z: z[0], reverse=True)
    if not scored:
        return {"resolved": False, "reason": "NO_CANDIDATES"}
    top_s, top = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if top_s < threshold:
        return {"resolved": False, "reason": "LOW_MATCH_SCORE", "top_score": top_s}
    if len(scored) > 1 and top_s - second < margin:
        return {"resolved": False, "reason": "AMBIGUOUS_MATCH", "top_score": top_s, "second_score": second}
    return {"resolved": True, "id": str(top["id"]), "score": top_s, "candidate": {k: top.get(k) for k in ("home", "away", "kickoff")}}


def resolve_espn(match: dict[str, Any], league_slug: str) -> dict[str, Any]:
    try:
        date = (_dt(match.get("kickoff")) or datetime.now(timezone.utc)).strftime("%Y%m%d")
        url = f"{ESPNLineupClient.BASE}/{league_slug}/scoreboard?dates={date}"
        payload = _json(url)
        r = best_fixture(match, _walk_events(payload))
        return {"source": "espn", **r, "league_slug": league_slug}
    except Exception as e:
        return {"source": "espn", "resolved": False, "reason": f"{type(e).__name__}: {e}"}


def resolve_fotmob(match: dict[str, Any], league_id: int) -> dict[str, Any]:
    try:
        payload = _json(f"{FotMobLineupClient.BASE}/leagues?id={int(league_id)}")
        r = best_fixture(match, _walk_events(payload))
        return {"source": "fotmob", **r, "league_id": league_id}
    except Exception as e:
        return {"source": "fotmob", "resolved": False, "reason": f"{type(e).__name__}: {e}"}


def resolve_flashscore(match: dict[str, Any]) -> dict[str, Any]:
    fs = FlashscoreClient()
    date = (_dt(match.get("kickoff")) or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    r = fs.matches(date=date)
    if not r.ok:
        return {"source": "flashscore", "resolved": False, "reason": r.error or "MATCH_LIST_FAILED"}
    out = best_fixture(match, _walk_events(r.data))
    return {"source": "flashscore", **out}


def resolve_pinnacle(match: dict[str, Any], league_id: int) -> dict[str, Any]:
    r = PinnaclePrematchClient().odds(int(league_id), None)
    if not r.ok:
        return {"source": "pinnacle", "resolved": False, "reason": r.error or "ODDS_FETCH_FAILED"}
    candidates = []
    seen = set()
    for row in r.data:
        eid = row.get("event_id")
        if eid in seen:
            continue
        seen.add(eid)
        candidates.append({"id": eid, "home": row.get("home"), "away": row.get("away"), "kickoff": row.get("start_time")})
    out = best_fixture(match, candidates)
    return {"source": "pinnacle", **out, "league_id": league_id}


def resolve_oddsharvester(match: dict[str, Any], date_yyyymmdd: str, league: str | None = None) -> dict[str, Any]:
    r = OddsHarvesterClient().upcoming(date_yyyymmdd, league=league)
    if not r.ok:
        return {"source": "oddsharvester", "resolved": False, "reason": r.error or "UPCOMING_FETCH_FAILED"}
    out = best_fixture(match, _walk_events(r.data))
    return {"source": "oddsharvester", **out}


def resolve_provider_ids(*, match: dict[str, Any], espn_league_slug: str | None = None,
                         fotmob_league_id: int | None = None, pinnacle_league_id: int | None = None,
                         date_yyyymmdd: str | None = None, odds_league: str | None = None) -> dict[str, Any]:
    """Resolve as many provider IDs as possible and expose every unresolved provider."""
    attempts: list[dict[str, Any]] = []
    ids: dict[str, Any] = {}

    if espn_league_slug:
        x = resolve_espn(match, espn_league_slug); attempts.append(x)
        ids["espn_league_slug"] = espn_league_slug
        if x.get("resolved"): ids["espn_event_id"] = x["id"]
    else:
        attempts.append({"source": "espn", "resolved": False, "reason": "ESPN_LEAGUE_SLUG_MISSING"})

    if fotmob_league_id is not None:
        x = resolve_fotmob(match, fotmob_league_id); attempts.append(x)
        if x.get("resolved"): ids["fotmob_match_id"] = x["id"]
    else:
        attempts.append({"source": "fotmob", "resolved": False, "reason": "FOTMOB_LEAGUE_ID_MISSING"})

    x = resolve_flashscore(match); attempts.append(x)
    if x.get("resolved"): ids["flashscore_match_id"] = x["id"]

    if pinnacle_league_id is not None:
        x = resolve_pinnacle(match, pinnacle_league_id); attempts.append(x)
        if x.get("resolved"): ids["pinnacle_matchup_id"] = x["id"]
    else:
        attempts.append({"source": "pinnacle", "resolved": False, "reason": "PINNACLE_LEAGUE_ID_MISSING"})

    if date_yyyymmdd:
        x = resolve_oddsharvester(match, date_yyyymmdd, odds_league); attempts.append(x)
        if x.get("resolved"): ids["oddsharvester_event_id"] = x["id"]
    else:
        attempts.append({"source": "oddsharvester", "resolved": False, "reason": "MATCH_DATE_MISSING"})

    return {
        "resolver_version": RESOLVER_VERSION,
        "resolved_ids": ids,
        "attempts": attempts,
        "resolved_sources": sorted([x["source"] for x in attempts if x.get("resolved")]),
        "unresolved": [{"source": x["source"], "reason": x.get("reason", "UNKNOWN")} for x in attempts if not x.get("resolved")],
    }
