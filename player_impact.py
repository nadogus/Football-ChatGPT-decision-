"""Player impact evidence for XI changes. Evidence only — never assigns PLAY/WATCH/PASS.

Question answered: when the official XI differs from the previous one, HOW MUCH does the change weigh?
For every player who dropped out of / came into the XI we report, from the team's last 5 and 10 matches
(FotMob match details, same unofficial source as fotmob_source.py):
  - minutes load and appearances,
  - per-90 xG, xA, shots, chances created,
  - share of the team's total xG+xA in that window (how much of the attack runs through him),
  - replacement gap: incoming minus outgoing, per 90.
Goalkeeper: one noisy line (goals prevented over the window, with sample size) — never a standalone signal.

Fails closed: any missing block yields None / a gap string, never an invented number.
Per-match player stats are market-priced form data; they are only meaningful as the WEIGHT of a late XI change.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Callable

IMPACT_VERSION = "PLAYER_IMPACT_V1.0"
WINDOWS = (5, 10)

# FotMob stat labels (matchDetails.content.playerStats[*].stats[*].stats) -> our keys
LABELS = {
    "minutes played": "minutes",
    "expected goals (xg)": "xg",
    "expected assists (xa)": "xa",
    "total shots": "shots",
    "chances created": "key_passes",
    "goals prevented": "goals_prevented",
    "saves": "saves",
}


def norm(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z ]+", " ", s).split())


def name_key(name: Any) -> str:
    """Last token (surname) of a normalized name; 'Salah M.' style keeps the first token."""
    parts = [p for p in norm(name).split() if len(p) > 1]
    if not parts:
        return ""
    return parts[0] if str(name).strip().endswith(".") else parts[-1]


def _num(v: Any) -> float | None:
    if isinstance(v, dict):
        v = v.get("value", v.get("stat"))
        if isinstance(v, dict):
            v = v.get("value")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_player_stats(details: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{fotmob_player_id: {name, team_id, minutes, xg, xa, shots, key_passes, ...}} from one finished match.

    Players with unreadable stats are skipped. Missing individual stats stay absent (not zero).
    """
    ps = ((details or {}).get("content") or {}).get("playerStats")
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(ps, dict):
        return out
    for pid, p in ps.items():
        if not isinstance(p, dict):
            continue
        rec: dict[str, Any] = {"name": p.get("name"), "team_id": p.get("teamId"), "is_gk": bool(p.get("isGoalkeeper"))}
        for grp in p.get("stats") or []:
            for label, val in ((grp or {}).get("stats") or {}).items():
                key = LABELS.get(str(label).strip().lower())
                if key and key not in rec:
                    n = _num(val)
                    if n is not None:
                        rec[key] = n
        if rec.get("minutes") is not None:
            out[str(pid)] = rec
    return out


def recent_match_ids(fixtures: list[dict[str, Any]], before: datetime, n: int = 10) -> list[Any]:
    """Newest-first ids of the team's last n FINISHED matches before `before`."""
    rows = []
    for f in fixtures or []:
        st = f.get("status") or {}
        if not st.get("finished"):
            continue
        try:
            when = datetime.fromisoformat(str(st.get("utcTime")).replace("Z", "+00:00"))
        except Exception:
            continue
        if when < before and f.get("id") is not None:
            rows.append((when, f["id"]))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [i for _, i in rows[:n]]


class TeamHistory:
    """Last-N finished matches of one team, as per-match player stat dicts (newest first)."""

    def __init__(self, team_id: Any, matches: list[dict[str, dict[str, Any]]], requested: int):
        self.team_id = team_id
        self.matches = matches          # only matches whose stats were readable
        self.requested = requested      # how many match ids we tried

    def window(self, n: int) -> list[dict[str, dict[str, Any]]]:
        return self.matches[:n]


def load_history(get: Callable[[str], Any], team_id: Any, before: datetime, n: int = 10) -> tuple[TeamHistory | None, str | None]:
    """Fetch team fixtures + each match's details. Returns (history, gap_reason)."""
    try:
        data = get(f"/teams?id={team_id}")
        fixtures = (((data or {}).get("fixtures") or {}).get("allFixtures") or {}).get("fixtures") or []
    except Exception as e:
        return None, f"TEAM_FIXTURES_ERROR:{type(e).__name__}"
    ids = recent_match_ids(fixtures, before, n)
    if not ids:
        return None, "NO_FINISHED_MATCHES_FOUND"
    matches = []
    for mid in ids:
        try:
            stats = parse_player_stats(get(f"/matchDetails?matchId={mid}"))
        except Exception:
            continue
        mine = {pid: s for pid, s in stats.items() if str(s.get("team_id")) == str(team_id)}
        if mine:
            matches.append(mine)
    if not matches:
        return None, "PLAYER_STATS_UNAVAILABLE"
    return TeamHistory(team_id, matches, len(ids)), None


def _find(match: dict[str, dict[str, Any]], pid: str | None, key: str) -> dict[str, Any] | None:
    if pid and pid in match:
        return match[pid]
    hits = [s for s in match.values() if name_key(s.get("name")) == key]
    return hits[0] if len(hits) == 1 else None


def player_profile(hist: TeamHistory, name: str, pid: str | None = None) -> dict[str, Any] | None:
    """Per-window load and per-90 production for one player; None if he never appears in the data."""
    key = name_key(name)
    pid = str(pid).replace("fotmob:", "") if pid and str(pid).startswith("fotmob:") else None
    out: dict[str, Any] = {"name": name, "windows": {}}
    seen = False
    for n in WINDOWS:
        ms = hist.window(n)
        mins = apps = 0.0
        tot = {"xg": 0.0, "xa": 0.0, "shots": 0.0, "key_passes": 0.0}
        team_xg_xa = 0.0
        for m in ms:
            team_xg_xa += sum((s.get("xg") or 0) + (s.get("xa") or 0) for s in m.values())
            s = _find(m, pid, key)
            if s and (s.get("minutes") or 0) > 0:
                seen = True
                apps += 1
                mins += s["minutes"]
                for k in tot:
                    tot[k] += s.get(k) or 0
        per90 = {k: round(v * 90 / mins, 2) for k, v in tot.items()} if mins else None
        share = round((tot["xg"] + tot["xa"]) / team_xg_xa, 3) if team_xg_xa else None
        out["windows"][str(n)] = {"matches_in_data": len(ms), "appearances": int(apps), "minutes": int(mins),
                                  "minutes_per_match": round(mins / len(ms), 1) if ms else None,
                                  "per90": per90, "attack_share": share}
    return out if seen else None


def gk_line(hist: TeamHistory, name: str, pid: str | None = None) -> dict[str, Any] | None:
    """Goals prevented over the available window. Deliberately minimal; small samples are noise."""
    key = name_key(name)
    pid = str(pid).replace("fotmob:", "") if pid and str(pid).startswith("fotmob:") else None
    gp = saves = 0.0
    games = 0
    for m in hist.window(10):
        s = _find(m, pid, key)
        if s and s.get("goals_prevented") is not None:
            games += 1
            gp += s["goals_prevented"]
            saves += s.get("saves") or 0
    if not games:
        return None
    return {"name": name, "games": games, "goals_prevented": round(gp, 2), "saves": int(saves),
            "note": "küçük örneklem, tek başına sinyal değil"}


def side_impact(hist: TeamHistory | None, ch: dict[str, Any] | None, now_xi: list[dict], prev_xi: list[dict] | None) -> dict[str, Any]:
    """Impact block for one team. `ch` is xi_watch.changes() output."""
    if hist is None:
        return {"status": "VERİ YOK"}
    if not ch:
        return {"status": "KADRO_FARKI_YOK_VERISI_YOK"}
    by_name = {name_key(p.get("name")): p for p in (now_xi or []) + (prev_xi or [])}
    res: dict[str, Any] = {"status": "OK", "history_matches": len(hist.matches), "out": [], "in": []}
    for tag in ("out", "in"):
        for nm in ch.get(tag) or []:
            p = by_name.get(name_key(nm)) or {}
            prof = player_profile(hist, nm, p.get("id"))
            res[tag].append(prof or {"name": nm, "windows": None, "note": "son maçlarda istatistik yok (yeni transfer / veri boşluğu)"})
    # replacement gap on the 10-match window, only when a 1:1 swap is meaningful
    gaps = []
    for o, i in zip(res["out"], res["in"]):
        wo, wi = (o.get("windows") or {}).get("10"), (i.get("windows") or {}).get("10")
        if wo and wi and wo.get("per90") and wi.get("per90"):
            gaps.append({"out": o["name"], "in": i["name"],
                         "delta_per90": {k: round(wi["per90"][k] - wo["per90"][k], 2) for k in wo["per90"]},
                         "attack_share_delta": None if wo["attack_share"] is None or wi["attack_share"] is None
                         else round(wi["attack_share"] - wo["attack_share"], 3)})
    res["replacement_gap"] = gaps
    if ch.get("goalkeeper_changed"):
        res["goalkeeper"] = {"now": gk_line(hist, ch.get("goalkeeper") or ""), "previous": gk_line(hist, ch.get("previous_goalkeeper") or "")}
    return res


def render_side(team: str, imp: dict[str, Any] | None) -> list[str]:
    if not imp or imp.get("status") != "OK":
        return [f"- {team}: oyuncu etkisi VERİ YOK ({(imp or {}).get('status', 'hesaplanmadı')})"]
    L = [f"- **{team}** (son {imp['history_matches']} maç verisi):"]
    for tag, label in (("out", "çıkan"), ("in", "giren")):
        for p in imp[tag]:
            w = (p.get("windows") or {})
            w5, w10 = w.get("5"), w.get("10")
            if not w10:
                L.append(f"  - {label}: {p['name']} — {p.get('note') or 'veri yok'}")
                continue
            per = w10["per90"] or {}
            L.append(f"  - {label}: {p['name']} — son 5: {w5['appearances']} maç/{w5['minutes']} dk · son 10: {w10['appearances']} maç/{w10['minutes']} dk"
                     + (f" · 90 dk başına xG {per['xg']}, xA {per['xa']}, şut {per['shots']}, kilit pas {per['key_passes']}" if per else "")
                     + (f" · takımın xG+xA'sının %{100 * w10['attack_share']:.0f}'i" if w10.get("attack_share") is not None else ""))
    for g in imp.get("replacement_gap") or []:
        d = g["delta_per90"]
        L.append(f"  - fark ({g['out']} → {g['in']}), 90 dk başına: xG {d['xg']:+}, xA {d['xa']:+}, şut {d['shots']:+}, kilit pas {d['key_passes']:+}")
    gk = imp.get("goalkeeper")
    if gk:
        f = lambda x: f"{x['name']}: {x['goals_prevented']:+} önlenen gol / {x['games']} maç" if x else "veri yok"
        L.append(f"  - kaleci: {f(gk.get('now'))} (önceki: {f(gk.get('previous'))}) — küçük örneklem, tek başına sinyal değil")
    return L


def build(get: Callable[[str], Any], details: dict[str, Any] | None, before: datetime, xi: dict[str, Any],
          changes: dict[str, Any], prev: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Whole-match impact block + gap strings. Never raises."""
    gaps: list[str] = []
    out: dict[str, Any] = {"version": IMPACT_VERSION}
    gen = (details or {}).get("general") or {}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        tid = (gen.get(key) or {}).get("id")
        try:
            ch = (changes or {}).get(side)
            if tid is None:
                out[side] = {"status": "VERİ YOK"}; gaps.append(f"PLAYER_IMPACT_NO_TEAM_ID:{side}")
                continue
            if not ch or not ch.get("count"):
                out[side] = {"status": "KADRO_FARKI_YOK" if ch else "ONCEKI_KADRO_YOK"}
                continue
            hist, why = load_history(get, tid, before, 10)
            if hist is None:
                out[side] = {"status": "VERİ YOK", "reason": why}; gaps.append(f"PLAYER_IMPACT_{why}:{side}")
                continue
            out[side] = side_impact(hist, ch, xi[side]["starters"], ((prev or {}).get(side) or {}).get("starters"))
            if hist.requested > len(hist.matches):
                gaps.append(f"PLAYER_IMPACT_PARTIAL_HISTORY:{side}:{len(hist.matches)}/{hist.requested}")
        except Exception as e:
            out[side] = {"status": "VERİ YOK", "reason": f"{type(e).__name__}"}
            gaps.append(f"PLAYER_IMPACT_ERROR:{side}:{type(e).__name__}")
    return out, gaps
