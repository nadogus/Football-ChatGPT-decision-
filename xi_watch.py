#!/usr/bin/env python3
"""Official XI watcher. Evidence only — never assigns PLAY/WATCH/PASS.

Runs every ~10 minutes. For each fixture of today (from daily/<date>/fixtures.json) whose
kickoff is 75..10 minutes away and whose XI is not yet confirmed:
  - Flashscore lineups: official only if BOTH sides have an exact "Starting Lineups" group
    with 11 players (predicted/expected groups are ignored),
  - ESPN cross-check by player surname (independent validator, when resolvable),
  - changes vs each team's previous starting XI, fresh missing-players list,
  - odds snapshot at XI time and movement since the morning scan,
then writes daily/<date>/xi/<match_id>.json + .md and notifies (Slack webhook / ntfy, optional).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data_adapters import ESPNLineupClient, FlashscoreClient, normalize_decimal_quotes
from daily_pipeline import TSI, append_jsonl, league_match, load_leagues
from fixture_resolver import resolve_espn
from market_evidence import market_summary
from public_sources import FlashscoreModelClient

WATCH_VERSION = "XI_WATCH_V1.0"
ROOT = Path(os.getenv("PIPELINE_ROOT", "."))
ODDS_GEO = os.getenv("ODDS_GEO", "GB")
WINDOW = (10, 75)  # minutes before kickoff
OFFICIAL_GROUPS = {"starting lineups", "starting lineup", "starting xi"}


def surname(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    parts = [p for p in re.sub(r"[^a-z ]+", " ", s).split() if len(p) > 1]
    if not parts:
        return ""
    # Flashscore uses "Salah M." -> first token; ESPN uses "Mohamed Salah" -> last token.
    return parts[0] if str(name).strip().endswith(".") else parts[-1]


def official_xi(payload: dict[str, Any]) -> dict[str, Any]:
    """Strict: exact official group name, exactly 11 starters per side."""
    out: dict[str, Any] = {"official": False}
    for side in ("home", "away"):
        block = (payload or {}).get(side) or {}
        groups = [g for g in block.get("groups") or [] if str(g.get("name") or "").strip().lower() in OFFICIAL_GROUPS]
        players = groups[0]["players"] if groups else []
        out[side] = {"formation": block.get("formation"), "group": groups[0]["name"] if groups else None,
                     "starters": [{"id": (p.get("player") or {}).get("id"), "name": (p.get("player") or {}).get("name"),
                                   "number": p.get("shirt_number"), "gk": bool(p.get("is_goalkeeper")),
                                   "captain": bool(p.get("is_captain"))} for p in players],
                     "other_groups": [g.get("name") for g in block.get("groups") or [] if g not in groups]}
    out["official"] = len(out["home"]["starters"]) == 11 and len(out["away"]["starters"]) == 11
    out["reason"] = "OFFICIAL_11_PLUS_11" if out["official"] else "NOT_OFFICIAL_OR_INCOMPLETE"
    return out


def espn_starter_names(summary: dict[str, Any]) -> list[str]:
    names = []
    def walk(x):
        if isinstance(x, dict):
            a = x.get("athlete") if isinstance(x.get("athlete"), dict) else None
            if a and (x.get("starter") is True or x.get("isStarter") is True):
                names.append(a.get("displayName") or a.get("fullName") or a.get("lastName"))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(summary)
    return [n for n in dict.fromkeys(names) if n]


def espn_xi(summary: dict[str, Any]) -> dict[str, Any]:
    """ESPN match summary -> same shape as official_xi(). ESPN lists rosters once lineups are published."""
    out: dict[str, Any] = {"official": False, "source": "espn"}
    for side in ("home", "away"):
        out[side] = {"formation": None, "group": None, "starters": [], "other_groups": []}
    for r in (summary or {}).get("rosters") or []:
        side = r.get("homeAway")
        if side not in ("home", "away"):
            continue
        starters = []
        for p in r.get("roster") or []:
            if p.get("starter") is not True:
                continue
            a = p.get("athlete") or {}
            pos = str(((p.get("position") or {}).get("abbreviation")) or "").upper()
            starters.append({"id": f"espn:{a.get('id')}", "name": a.get("displayName") or a.get("fullName"),
                             "number": p.get("jersey"), "gk": pos in ("G", "GK"), "captain": bool(p.get("captain"))})
        out[side] = {"formation": r.get("formation") if isinstance(r.get("formation"), str) else (r.get("formation") or {}).get("name") if isinstance(r.get("formation"), dict) else None,
                     "group": "ESPN starters" if starters else None, "starters": starters, "other_groups": []}
    out["official"] = len(out["home"]["starters"]) == 11 and len(out["away"]["starters"]) == 11
    out["reason"] = "OFFICIAL_11_PLUS_11_ESPN" if out["official"] else "ESPN_LINEUP_NOT_PUBLISHED"
    return out


def same_team(a: Any, b: Any) -> bool:
    from fixture_resolver import _team_score
    return _team_score(a, b) >= 0.86


def espn_previous_xi(slug: str, team: str, before: datetime) -> dict[str, Any] | None:
    """Team's previous starting XI from its last completed league match on ESPN (last 21 days)."""
    from data_adapters import _json
    start = (before - timedelta(days=21)).strftime("%Y%m%d"); end = (before - timedelta(days=1)).strftime("%Y%m%d")
    data = _json(f"{ESPNLineupClient.BASE}/{slug}/scoreboard?dates={start}-{end}&limit=500")
    best = None
    for e in (data or {}).get("events") or []:
        if not (((e.get("status") or {}).get("type") or {}).get("completed")):
            continue
        comp = (e.get("competitions") or [{}])[0]
        for c in comp.get("competitors") or []:
            name = (c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name")
            if same_team(name, team):
                when = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
                opp = next(((x.get("team") or {}).get("displayName") for x in comp.get("competitors") or [] if x is not c), None)
                if when < before and (best is None or when > best[0]):
                    best = (when, e.get("id"), c.get("homeAway"), opp)
    if not best:
        return None
    when, eid, side, opp = best
    s = ESPNLineupClient().summary(slug, eid)
    if not s.ok:
        return None
    x = espn_xi(s.data)
    if len(x[side]["starters"]) != 11:
        return None
    return {"match_id": f"espn:{eid}", "date": when.isoformat(), "competition": slug, "opponent": opp,
            "starters": x[side]["starters"], "formation": x[side]["formation"]}


def cross_check(xi: dict[str, Any], espn_names: list[str]) -> dict[str, Any]:
    if len(espn_names) < 22:
        return {"validated": False, "reason": "ESPN_LINEUP_NOT_AVAILABLE", "espn_count": len(espn_names)}
    espn = {surname(n) for n in espn_names}
    fs = [surname(p["name"]) for side in ("home", "away") for p in xi[side]["starters"]]
    hit = sum(1 for s in fs if s in espn)
    share = hit / len(fs) if fs else 0
    return {"validated": share >= 0.8, "matched_share": round(share, 3), "espn_count": len(espn_names),
            "reason": "ESPN_AGREES" if share >= 0.8 else "ESPN_DISAGREES"}


def previous_xi(model: FlashscoreModelClient, fs: FlashscoreClient, team: str, before: datetime) -> dict[str, Any] | None:
    tid = model.team_id(team)
    if not tid:
        return None
    r = fs.team_results(tid, page=1)
    if not r.ok:
        return None
    rows = []
    for block in (r.data or {}).get("competitions") or []:
        for m in block.get("matches") or []:
            try:
                when = datetime.fromisoformat(str(m.get("start_time")).replace("Z", "+00:00"))
            except Exception:
                continue
            if when < before - timedelta(hours=3):
                rows.append((when, m, (block.get("competition") or {}).get("name")))
    if not rows:
        return None
    when, m, comp = max(rows, key=lambda z: z[0])
    lu = fs.lineups(str(m.get("id")))
    if not lu.ok:
        return None
    side = "home" if str((m.get("home") or {}).get("id")) == str(tid) else "away"
    x = official_xi(lu.data)
    if len(x[side]["starters"]) != 11:
        return None
    return {"match_id": m.get("id"), "date": when.isoformat(), "competition": comp,
            "opponent": (m.get("away" if side == "home" else "home") or {}).get("name"), "starters": x[side]["starters"],
            "formation": x[side]["formation"]}


def changes(now: list[dict], prev: list[dict] | None) -> dict[str, Any] | None:
    if not prev:
        return None
    key = lambda p: p.get("id") or surname(p.get("name"))
    a, b = {key(p): p for p in now}, {key(p): p for p in prev}
    out = [b[k]["name"] for k in b if k not in a]
    inn = [a[k]["name"] for k in a if k not in b]
    gk_now = next((p for p in now if p.get("gk")), None)
    gk_prev = next((p for p in prev if p.get("gk")), None)
    return {"count": len(inn), "out": out, "in": inn,
            "goalkeeper_changed": bool(gk_now and gk_prev and key(gk_now) != key(gk_prev)),
            "goalkeeper": (gk_now or {}).get("name"), "previous_goalkeeper": (gk_prev or {}).get("name")}


def render(rec: dict[str, Any]) -> str:
    m, x = rec["match"], rec["xi"]
    k = datetime.fromisoformat(str(m["kickoff"]).replace("Z", "+00:00"))
    L = [f"## {m['home']} – {m['away']} · resmi kadrolar", "",
         f"{m['competition']} · {k:%H:%M} UTC / {k.astimezone(TSI):%H:%M} TSİ · çekildi {rec['observed_at'][11:16]} UTC "
         f"(maça {rec['minutes_before_kickoff']:.0f} dk) · kaynak: ESPN · çapraz kontrol: {rec['validation']['reason']}", ""]
    for side, team in (("home", m["home"]), ("away", m["away"])):
        s = x[side]
        L.append(f"**{team}** ({s['formation'] or 'diziliş ?'}): " + ", ".join(
            p["name"] + (" (K)" if p["gk"] else "") + (" (C)" if p["captain"] else "") for p in s["starters"]))
        ch = rec["changes"].get(side)
        if ch:
            L.append(f"- Önceki maça göre ({rec['previous'][side]['date'][:10]}, {rec['previous'][side]['opponent']}): "
                     f"{ch['count']} değişiklik" + (f" · çıkan: {', '.join(ch['out'])} · giren: {', '.join(ch['in'])}" if ch["count"] else "")
                     + (f" · **kaleci değişti** ({ch['previous_goalkeeper']} → {ch['goalkeeper']})" if ch["goalkeeper_changed"] else ""))
        else:
            L.append("- Önceki kadro bulunamadı (fark hesaplanmadı)")
        mp = (rec.get("missing_players") or {}).get(side)
        L.append("- Eksikler: " + (", ".join(f"{r['player']} ({r.get('reason') or '?'})" for r in mp) if mp else "VERİ YOK (kaynak boş döndü; 'eksik yok' anlamına gelmez)"))
    mk = (rec.get("market") or {}).get("1x2")
    if mk:
        mv = rec.get("movement_since_scan_pp")
        L.append("")
        L.append(f"**Piyasa şimdi (marjsız):** 1 %{100 * mk['consensus_fair']['HOME']:.1f} · X %{100 * mk['consensus_fair']['DRAW']:.1f} · "
                 f"2 %{100 * mk['consensus_fair']['AWAY']:.1f}" + (f" · sabah taramasından beri: 1 {mv['HOME']:+.1f} · X {mv['DRAW']:+.1f} · 2 {mv['AWAY']:+.1f} puan" if mv else ""))
        b = mk["best_price"]
        L.append(f"**En iyi oran:** 1 {b['HOME']['odds']} ({b['HOME']['bookmaker']}) · X {b['DRAW']['odds']} ({b['DRAW']['bookmaker']}) · 2 {b['AWAY']['odds']} ({b['AWAY']['bookmaker']})")
    if rec.get("gaps"):
        L.append(f"\nEksik veri: {', '.join(rec['gaps'])}")
    L.append("\n_Kanıttır, karar değildir._")
    return "\n".join(L)


def notify(text: str, title: str):
    sent = []
    hook = os.getenv("SLACK_WEBHOOK_URL")
    if hook:
        try:
            body = json.dumps({"text": text[:3500]}).encode()
            urllib.request.urlopen(urllib.request.Request(hook, body, {"Content-Type": "application/json"}), timeout=20)
            sent.append("slack")
        except Exception as e:
            print("slack notify failed:", type(e).__name__)
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        try:
            urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", text[:3500].encode(),
                                                          {"Title": title.encode("ascii", "ignore").decode() or "XI"}), timeout=20)
            sent.append("ntfy")
        except Exception as e:
            print("ntfy notify failed:", type(e).__name__)
    return sent


class Watcher:
    def __init__(self, fs: FlashscoreClient | None = None):
        self.fs = fs or FlashscoreClient()
        self.model = FlashscoreModelClient(self.fs.base)
        self.leagues = load_leagues()

    def process(self, fx: dict[str, Any], day_dir: Path, now: datetime, force: bool = False) -> dict[str, Any] | None:
        """ESPN is the primary XI source (Flashscore's lineups feed currently returns empty);
        Flashscore is used as an independent cross-check whenever it returns data."""
        kickoff = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
        gaps = []
        lg = league_match({"name": fx["competition"], "category": fx["category"]}, self.leagues) or {}
        slug = lg.get("espn")
        if not slug:
            return {"status": "NO_ESPN_SLUG"}
        res = resolve_espn(fx, slug)
        if not res.get("resolved"):
            return {"status": "ESPN_UNRESOLVED", "error": res.get("reason")}
        s = ESPNLineupClient().summary(slug, res["id"])
        if not s.ok:
            return {"status": "ESPN_SUMMARY_FAILED", "error": s.error}
        xi = espn_xi(s.data)
        if not xi["official"] and not force:
            return {"status": "NOT_YET", "groups": [len(xi["home"]["starters"]), len(xi["away"]["starters"])]}
        lu = self.fs.lineups(fx["match_id"])
        fs_xi = official_xi(lu.data) if lu.ok else {"official": False}
        if fs_xi.get("official"):
            fs_names = [p["name"] for side in ("home", "away") for p in fs_xi[side]["starters"]]
            validation = cross_check(xi, fs_names)
            validation["reason"] = "FLASHSCORE_AGREES" if validation["validated"] else "FLASHSCORE_DISAGREES"
        else:
            validation = {"validated": False, "reason": "FLASHSCORE_LINEUPS_EMPTY"}
            gaps.append("XI_SINGLE_SOURCE:ESPN_ONLY")
        prev = {}
        for side in ("home", "away"):
            err = ""
            try:
                prev[side] = espn_previous_xi(slug, fx[side], kickoff)
            except Exception as e:
                prev[side] = None; err = f":{type(e).__name__}:{str(e)[:80]}"
            if not prev[side]:
                gaps.append(f"PREVIOUS_XI_UNAVAILABLE:{side}{err}")
        mp = self.fs.missing_players(fx["match_id"])
        missing = {k: [{"player": (r.get("player") or {}).get("name"), "reason": r.get("reason"), "likelihood": r.get("likelihood")}
                       for r in ((mp.data or {}).get(k) or [])] for k in ("home", "away")} if mp.ok else {}
        if not any(missing.values()):
            missing = {}
            gaps.append("MISSING_PLAYERS_SOURCE_EMPTY")
        o = self.fs.odds(fx["match_id"], geo=ODDS_GEO)
        mk = market_summary(normalize_decimal_quotes(o.data, "flashscore")) if o.ok else {}
        mv = None
        pk = day_dir / "packets" / f"{fx['match_id']}.json"
        if pk.exists() and mk.get("1x2"):
            morning = ((json.loads(pk.read_text(encoding="utf-8")).get("market") or {}).get("summary") or {}).get("1x2")
            if morning:
                mv = {s: round(100 * (mk["1x2"]["consensus_fair"][s] - morning["consensus_fair"][s]), 2) for s in ("HOME", "DRAW", "AWAY")}
        live = xi["official"] and now < kickoff  # a past match is only ever a pipeline validation
        rec = {"event": "POST_XI_EVIDENCE" if live else "XI_VALIDATION_ONLY", "watch_version": WATCH_VERSION,
               "observed_at": now.isoformat(), "minutes_before_kickoff": (kickoff - now).total_seconds() / 60,
               "match": {k: fx.get(k) for k in ("match_id", "home", "away", "kickoff", "competition", "category")},
               "xi": xi, "validation": validation, "previous": prev,
               "changes": {s: changes(xi[s]["starters"], (prev.get(s) or {}).get("starters")) for s in ("home", "away")},
               "missing_players": missing, "market": mk, "movement_since_scan_pp": mv, "gaps": gaps,
               "decision_authority": "CHATGPT_ONLY", "production_decision": None}
        (day_dir / "xi").mkdir(parents=True, exist_ok=True)
        (day_dir / "xi" / f"{fx['match_id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        md = render(rec)
        (day_dir / "xi" / f"{fx['match_id']}.md").write_text(md + "\n", encoding="utf-8")
        if live:
            append_jsonl(ROOT / "ledger" / "post_xi_evidence.jsonl", rec)
        rec["_md"] = md
        return {"status": "CONFIRMED" if live else "VALIDATION", "record": rec}


def run(now: datetime | None = None, day: str | None = None, match_id: str | None = None, force: bool = False):
    now = now or datetime.now(timezone.utc)
    days = [day] if day else sorted({now.date().isoformat(), (now - timedelta(hours=12)).date().isoformat()})
    w = None
    for d in days:
        day_dir = ROOT / "daily" / d
        fx_path = day_dir / "fixtures.json"
        if not fx_path.exists():
            continue
        state_path = day_dir / "xi_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        for fx in json.loads(fx_path.read_text(encoding="utf-8")):
            mid = fx["match_id"]
            if match_id and mid != match_id:
                continue
            if not match_id and (state.get(mid) or {}).get("status") == "CONFIRMED":
                continue
            kickoff = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
            mins = (kickoff - now).total_seconds() / 60
            if not match_id and not (WINDOW[0] <= mins <= WINDOW[1]):
                if mins < WINDOW[0] and (state.get(mid) or {}).get("status") not in ("CONFIRMED", "MISSED"):
                    if (state.get(mid) or {}).get("checks"):
                        state[mid] = {**state.get(mid, {}), "status": "MISSED", "note": "official XI not seen before kickoff-10"}
                continue
            w = w or Watcher()
            res = w.process(fx, day_dir, now, force=force) or {}
            st = state.get(mid) or {"checks": 0}
            st.update({"status": res.get("status"), "checks": st.get("checks", 0) + 1, "last_check": now.isoformat()})
            state[mid] = st
            print(f"{fx['home']} - {fx['away']} ({mins:.0f} dk): {res.get('status')} {res.get('error') or res.get('groups') or ''}")
            if res.get("status") == "CONFIRMED":
                rec = res["record"]
                sent = notify(rec["_md"], f"XI: {fx['home']} - {fx['away']}")
                st["notified"] = sent
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--match-id")
    ap.add_argument("--force", action="store_true", help="validation only: process even if not official / outside window")
    a = ap.parse_args()
    run(day=a.date, match_id=a.match_id, force=a.force)


if __name__ == "__main__":
    main()
