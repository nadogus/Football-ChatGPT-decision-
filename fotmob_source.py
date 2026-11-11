"""FotMob public web data: absences (injury/suspension + expected return) and lineups.

Unofficial endpoints (no key, matched by team names + kickoff) used by fotmob.com itself; they can change without notice,
so every call fails closed and reports the reason. Evidence only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fixture_resolver import best_fixture

BASE = "https://www.fotmob.com/api/data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json"}


def _get(path: str, timeout: float = 25.0) -> Any:
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class FotMobClient:
    def __init__(self, getter=None):
        self.get = getter or _get
        self._days: dict[str, list[dict[str, Any]]] = {}

    def matches(self, day: str) -> list[dict[str, Any]]:
        """day = YYYY-MM-DD -> [{id, home, away, kickoff, league}]"""
        if day not in self._days:
            data = self.get(f"/matches?date={day.replace('-', '')}")
            rows = []
            for lg in (data or {}).get("leagues") or []:
                for m in lg.get("matches") or []:
                    rows.append({"id": m.get("id"), "home": (m.get("home") or {}).get("name"),
                                 "away": (m.get("away") or {}).get("name"),
                                 "kickoff": (m.get("status") or {}).get("utcTime"), "league": lg.get("name")})
            self._days[day] = rows
        return self._days[day]

    def resolve(self, fx: dict[str, Any]) -> dict[str, Any]:
        day = str(fx["kickoff"])[:10]
        try:
            return best_fixture({"home": fx["home"], "away": fx["away"], "kickoff": fx["kickoff"]}, self.matches(day))
        except Exception as e:
            return {"resolved": False, "reason": f"{type(e).__name__}: {e}"}

    def details(self, match_id: Any) -> dict[str, Any]:
        return self.get(f"/matchDetails?matchId={match_id}")


def absences(details: dict[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    """{'home': [...], 'away': [...]} or None if the block is missing entirely."""
    lu = ((details or {}).get("content") or {}).get("lineup")
    if not isinstance(lu, dict):
        return None
    out = {}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        rows = []
        for u in ((lu.get(key) or {}).get("unavailable") or []):
            un = u.get("unavailability") or {}
            rows.append({"player": u.get("name"), "reason": un.get("type"),
                         "likelihood": un.get("expectedReturn"), "market_value_eur": u.get("marketValue")})
        out[side] = rows
    return out


def lineup(details: dict[str, Any]) -> dict[str, Any]:
    """Starting XIs as published by FotMob; predicted/unavailable types are never 'official'."""
    lu = ((details or {}).get("content") or {}).get("lineup") or {}
    ltype = str(lu.get("lineupType") or "").lower()
    out: dict[str, Any] = {"lineup_type": ltype or None, "source": lu.get("source")}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lu.get(key) or {}
        out[side] = {"formation": t.get("formation"),
                     "starters": [{"name": p.get("name"), "id": f"fotmob:{p.get('id')}"} for p in t.get("starters") or []]}
    out["official"] = (len(out["home"]["starters"]) == 11 and len(out["away"]["starters"]) == 11
                       and "predict" not in ltype and ltype != "unavailable")
    return out


def weather(details: dict[str, Any]) -> dict[str, Any] | None:
    w = ((details or {}).get("content") or {}).get("weather")
    return w if isinstance(w, dict) and w else None
