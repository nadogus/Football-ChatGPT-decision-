#!/usr/bin/env python3
"""Daily evidence pipeline. Evidence only — never assigns PLAY/WATCH/PASS.

  scan    : today's matches in the configured leagues -> per-match evidence packets + OZET.md
  settle  : after the day -> final scores + last pre-kickoff prices (closing) + CLV of recorded decisions
  record  : append a decision (made by ChatGPT/Claude/the user) BEFORE kickoff, with the price taken
  report  : decision ledger performance (ROI, CLV, drawdown)

Missing data is never fabricated: every gap is written into the packet and the summary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_match_packet import build_runtime_packet
from data_adapters import FlashscoreClient, normalize_decimal_quotes
from football_evidence_engine import ImmutableLedger, elo_1x2, scoreline_markets
from market_evidence import closing_line_value, market_fair_probability, market_summary
from public_sources import FlashscoreModelClient

PIPELINE_VERSION = "DAILY_PIPELINE_V1.0"
ROOT = Path(os.getenv("PIPELINE_ROOT", "."))
ODDS_GEO = os.getenv("ODDS_GEO", "GB")
TSI = timezone(timedelta(hours=3))
VARIANT = re.compile(r"\b(women|woman|u1\d|u2\d|youth|reserve|reserves|ii)\b", re.I)


def norm(x: Any) -> str:
    s = unicodedata.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def load_leagues(path: Path | None = None) -> list[dict[str, str]]:
    path = path or ROOT / "config" / "leagues.json"
    return json.loads(path.read_text(encoding="utf-8"))["leagues"]


def league_match(competition: dict[str, Any] | None, leagues: list[dict[str, str]]) -> dict[str, str] | None:
    """Exact category + name match; never matches women/youth variants (Austria's Bundesliga
    is not Germany's, 'Premier League' of another country is rejected by category)."""
    if not competition:
        return None
    name = competition.get("name") or ""
    cat = competition.get("category") or (competition.get("country") or {}).get("name") or ""
    if VARIANT.search(name) or VARIANT.search(competition.get("display_name") or ""):
        return None
    for lg in leagues:
        if norm(lg["category"]) == norm(cat) and norm(lg["name"]) == norm(name):
            return lg
    return None


# ---------------------------------------------------------------- weather (Open-Meteo, keyless)
def _get_json(url: str, timeout: float = 30.0, retries: int = 3) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "football-chatgpt-decision/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def weather_at(city: str | None, kickoff_utc: datetime) -> dict[str, Any]:
    if not city:
        return {"ok": False, "reason": "VENUE_CITY_UNKNOWN"}
    try:
        g = _get_json("https://geocoding-api.open-meteo.com/v1/search?" +
                      urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"}))
        res = (g or {}).get("results") or []
        if not res:
            return {"ok": False, "reason": "GEOCODE_NOT_FOUND", "city": city}
        lat, lon = res[0]["latitude"], res[0]["longitude"]
        day = kickoff_utc.date().isoformat()
        f = _get_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "UTC", "start_date": day, "end_date": day,
            "hourly": "temperature_2m,precipitation,precipitation_probability,wind_speed_10m"}))
        h = f.get("hourly") or {}
        target = kickoff_utc.strftime("%Y-%m-%dT%H:00")
        if target not in (h.get("time") or []):
            return {"ok": False, "reason": "FORECAST_HOUR_MISSING", "city": city}
        i = h["time"].index(target)
        return {"ok": True, "source": "open-meteo", "scope": "city-level forecast at kickoff hour",
                "city": city, "country": res[0].get("country"), "lat": lat, "lon": lon,
                "temperature_c": h["temperature_2m"][i], "precipitation_mm": h["precipitation"][i],
                "precipitation_probability_pct": (h.get("precipitation_probability") or [None] * (i + 1))[i],
                "wind_kmh": h["wind_speed_10m"][i], "observed_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "city": city}


# ---------------------------------------------------------------- scan
class Scanner:
    def __init__(self, fs: FlashscoreClient | None = None, pause: float = 0.3):
        self.fs = fs or FlashscoreClient()
        self.model = FlashscoreModelClient(self.fs.base)
        self.pause = pause
        self._elo_cache: dict[str, dict[str, float]] = {}
        self._venue_cache: dict[str, Any] = {}

    def _sleep(self):
        if self.pause:
            time.sleep(self.pause)

    def fixtures(self, day: str, leagues) -> list[dict[str, Any]]:
        r = self.fs.matches("football", day)
        if not r.ok:
            raise RuntimeError(f"FLASHSCORE_MATCH_LIST_FAILED: {r.error}")
        out = []
        for group in (r.data or {}).get("competitions") or []:
            comp = group.get("competition") or {}
            lg = league_match(comp, leagues)
            if not lg:
                continue
            for m in group.get("matches") or []:
                out.append({"match_id": str(m.get("id")), "home": (m.get("home") or {}).get("name"),
                            "away": (m.get("away") or {}).get("name"),
                            "home_team_id": (m.get("home") or {}).get("id"),
                            "away_team_id": (m.get("away") or {}).get("id"),
                            "kickoff": m.get("start_time"), "status": m.get("status"),
                            "competition": comp.get("name"), "category": comp.get("category") or lg["category"],
                            "link": m.get("link")})
        out.sort(key=lambda x: (x["kickoff"] or "", x["competition"] or ""))
        return out

    def venue_city(self, team_id: str | None) -> str | None:
        if not team_id:
            return None
        if team_id not in self._venue_cache:
            r = self.fs._get("/teams/details", {"team": team_id})
            self._sleep()
            self._venue_cache[team_id] = ((r.data or {}).get("venue") or {}).get("city") if r.ok else None
        return self._venue_cache[team_id]

    def elo(self, fx, as_of) -> tuple[float | None, float | None]:
        key = f"{fx['category']}|{fx['competition']}"
        if key not in self._elo_cache:
            try:
                self._elo_cache[key] = self.model.computed_elo(fx["home"], fx["competition"], as_of)
            except Exception:
                self._elo_cache[key] = {}
        ratings = self._elo_cache[key]
        pick = lambda team: next((v for k, v in ratings.items() if norm(k) == norm(team)), None)
        return pick(fx["home"]), pick(fx["away"])

    def evidence(self, fx: dict[str, Any]) -> dict[str, Any]:
        gaps: list[str] = []
        now = datetime.now(timezone.utc).isoformat()
        kickoff = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
        # odds (current + opening)
        r = self.fs.odds(fx["match_id"], geo=ODDS_GEO); self._sleep()
        quotes = normalize_decimal_quotes(r.data, "flashscore", include_opening=True) if r.ok else []
        if not r.ok:
            gaps.append(f"ODDS_FAILED:{r.error}")
        elif not quotes:
            gaps.append("ODDS_EMPTY")
        bookmakers = sorted({q["bookmaker"] for q in quotes})
        # injuries / suspensions
        mp = self.fs.missing_players(fx["match_id"]); self._sleep()
        missing = {"home": [], "away": []}
        if mp.ok:
            for side in ("home", "away"):
                for row in (mp.data or {}).get(side) or []:
                    missing[side].append({"player": ((row.get("player") or {}).get("name")),
                                          "reason": row.get("reason"), "likelihood": row.get("likelihood")})
        else:
            gaps.append(f"MISSING_PLAYERS_FAILED:{mp.error}")
        if mp.ok and not (missing["home"] or missing["away"]):
            missing = None  # Flashscore df_scr feed currently returns empty: unknown, NOT "no absences"
            gaps.append("MISSING_PLAYERS_SOURCE_EMPTY")
        # xG (Flashscore match statistics, last 6 competition matches before kickoff)
        hx = ax = None
        try:
            hx = self.model.team_xg_summary(fx["home"], fx["competition"], kickoff, last_n=6)
            ax = self.model.team_xg_summary(fx["away"], fx["competition"], kickoff, last_n=6)
        except Exception as e:
            gaps.append(f"XG_ERROR:{type(e).__name__}")
        if not (hx and ax):
            gaps.append("XG_UNAVAILABLE")
        he, ae = self.elo(fx, kickoff)
        if he is None or ae is None:
            gaps.append("ELO_UNAVAILABLE")
        weather = weather_at(self.venue_city(fx.get("home_team_id")), kickoff)
        if not weather.get("ok"):
            gaps.append(f"WEATHER_UNAVAILABLE:{weather.get('reason')}")
        models = {}
        if hx and ax:
            lam_h = (hx["xg_for"] + ax["xg_against"]) / 2
            lam_a = (ax["xg_for"] + hx["xg_against"]) / 2
            models["dixon_coles_xg"] = scoreline_markets(lam_h, lam_a)
        if he is not None and ae is not None:
            models["elo_season"] = elo_1x2(he, ae)
        sources = [{"source": "flashscore", "observed_at": now, "data": {"match_id": fx["match_id"]}}]
        if weather.get("ok"):
            sources.append({"source": "open-meteo", "observed_at": weather["observed_at"], "data": {}})
        packet = build_runtime_packet(
            match={"match_id": fx["match_id"], "home": fx["home"], "away": fx["away"], "kickoff": fx["kickoff"],
                   "competition": fx["competition"], "category": fx["category"]},
            models=models, source_payloads=sources,
            odds_payload={"primary_source": "flashscore", "observed_at": now, "quotes": quotes},
            context={"pipeline_version": PIPELINE_VERSION, "odds_geo": ODDS_GEO, "bookmakers": bookmakers,
                     "missing_players": missing, "xg": {"home": hx, "away": ax},
                     "elo": {"home": he, "away": ae, "method": "season-only results, start 1500"},
                     "weather": weather, "data_gaps": gaps,
                     "model_note": "Kaba modeller (xG ortalaması, sezon içi Elo). Kanıt olarak değerlendir; piyasaya karşı doğrulanmamıştır."},
            engine_version="evidence-v1.2")
        packet["event"] = "PRE_EVIDENCE_READY" if quotes else "PRE_EVIDENCE_INCOMPLETE"
        return packet


def pct(x):
    return "—" if x is None else f"%{100 * x:.1f}"


def render_match(p: dict[str, Any]) -> str:
    m, ctx, mk = p["match"], p.get("context") or {}, (p.get("market") or {}).get("summary") or {}
    k = datetime.fromisoformat(str(m["kickoff"]).replace("Z", "+00:00"))
    L = [f"### {m['home']} – {m['away']}  ·  {m['competition']} ({m.get('category')})",
         f"Başlama: {k:%H:%M} UTC / {k.astimezone(TSI):%H:%M} TSİ · Flashscore ID `{m['match_id']}`"]
    x = mk.get("1x2")
    if x:
        mv = x.get("movement_pp")
        L.append(f"- **1X2 piyasa (marjsız, {x['bookmakers']} bahisçi):** 1 {pct(x['consensus_fair']['HOME'])} · "
                 f"X {pct(x['consensus_fair']['DRAW'])} · 2 {pct(x['consensus_fair']['AWAY'])}"
                 + (f" | Pinnacle: 1 {pct(x['pinnacle_fair']['HOME'])} · X {pct(x['pinnacle_fair']['DRAW'])} · 2 {pct(x['pinnacle_fair']['AWAY'])}" if x.get("pinnacle_fair") else "")
                 + (f" | açılıştan hareket: 1 {mv['HOME']:+.1f} · X {mv['DRAW']:+.1f} · 2 {mv['AWAY']:+.1f} puan" if mv else " | açılış verisi yok"))
        b = x["best_price"]
        L.append(f"- **En iyi oran:** 1 {b['HOME']['odds']} ({b['HOME']['bookmaker']}) · X {b['DRAW']['odds']} ({b['DRAW']['bookmaker']}) · "
                 f"2 {b['AWAY']['odds']} ({b['AWAY']['bookmaker']}) · ort. marj %{100 * x['median_overround']:.1f}")
    else:
        L.append("- **1X2 piyasa:** YOK")
    t = (mk.get("totals") or {}).get("2.5")
    if t:
        L.append(f"- **Alt/Üst 2.5 (marjsız):** Üst {pct(t['consensus_fair']['OVER'])} · Alt {pct(t['consensus_fair']['UNDER'])} | "
                 f"en iyi Üst {t['best_price']['OVER']['odds']} ({t['best_price']['OVER']['bookmaker']}) · "
                 f"Alt {t['best_price']['UNDER']['odds']} ({t['best_price']['UNDER']['bookmaker']})")
    ens = (p.get("models") or {}).get("ensemble") or {}
    if ens.get("HOME") is not None:
        cands = {c["selection"]: c for c in (p.get("market") or {}).get("candidates") or []}
        lab = {"HOME": "1", "DRAW": "X", "AWAY": "2"}
        diff = " · ".join(f"{lab[s]} {cands[s]['model_minus_market_pp']:+.1f}"
                          for s in ("HOME", "DRAW", "AWAY") if s in cands and cands[s].get("model_minus_market_pp") is not None)
        L.append(f"- **Model (kaba, {', '.join((p['models'].get('individual') or {}).keys())}):** 1 {pct(ens.get('HOME'))} · "
                 f"X {pct(ens.get('DRAW'))} · 2 {pct(ens.get('AWAY'))}" + (f" | model−piyasa: {diff} puan" if diff else ""))
    xg = ctx.get("xg") or {}
    if xg.get("home") and xg.get("away"):
        L.append(f"- **xG (son {xg['home']['matches']}/{xg['away']['matches']} lig maçı ort., atılan/yenen):** "
                 f"ev {xg['home']['xg_for']:.2f}/{xg['home']['xg_against']:.2f} · dep {xg['away']['xg_for']:.2f}/{xg['away']['xg_against']:.2f}")
    elo = ctx.get("elo") or {}
    if elo.get("home") is not None and elo.get("away") is not None:
        L.append(f"- **Elo (sezon içi):** ev {elo['home']:.0f} · dep {elo['away']:.0f}")
    mp = ctx.get("missing_players")
    fmt = lambda rows: ", ".join(f"{r['player']} ({r.get('reason') or '?'}{'; ' + r['likelihood'] if r.get('likelihood') else ''})" for r in rows) or "listede yok"
    if mp:
        L.append(f"- **Eksikler:** ev: {fmt(mp.get('home') or [])} | dep: {fmt(mp.get('away') or [])}")
    else:
        L.append("- **Eksikler:** VERİ YOK (kaynak boş döndü; 'eksik yok' anlamına gelmez)")
    w = ctx.get("weather") or {}
    if w.get("ok"):
        L.append(f"- **Hava ({w['city']}, maç saati tahmini):** {w['temperature_c']}°C · yağış {w['precipitation_mm']} mm"
                 + (f" (%{w['precipitation_probability_pct']})" if w.get("precipitation_probability_pct") is not None else "")
                 + f" · rüzgâr {w['wind_kmh']} km/s")
    if ctx.get("data_gaps"):
        L.append(f"- **Eksik veri:** {', '.join(ctx['data_gaps'])}")
    return "\n".join(L)


def cmd_scan(day: str, limit: int | None = None, include_finished: bool = False):
    """include_finished is ONLY for pipeline validation on past days: such packets are marked
    VALIDATION_ONLY because their 'current' odds are post-match prices."""
    sc = Scanner()
    leagues = load_leagues()
    fxs = [f for f in sc.fixtures(day, leagues)
           if include_finished or f["status"] in (None, "scheduled", "not started", "NS")]
    if limit:
        fxs = fxs[:limit]
    out = ROOT / "daily" / day
    (out / "packets").mkdir(parents=True, exist_ok=True)
    (out / "fixtures.json").write_text(json.dumps(fxs, ensure_ascii=False, indent=1), encoding="utf-8")
    ledger = ImmutableLedger(str(ROOT / "ledger" / "pre_evidence.jsonl"))
    rendered = []
    for i, fx in enumerate(fxs, 1):
        print(f"[{i}/{len(fxs)}] {fx['home']} - {fx['away']} ({fx['competition']})", flush=True)
        try:
            p = sc.evidence(fx)
        except Exception as e:
            rendered.append(f"### {fx['home']} – {fx['away']}\n- **HATA:** {type(e).__name__}: {e}")
            continue
        if fx.get("status") == "finished":
            p["event"] = "VALIDATION_ONLY_POST_MATCH"
            p.setdefault("warnings", []).append("VALIDATION_ONLY: match already finished; prices are post-match, not bettable")
        p["ledger_sha256"] = ledger.append(p) if p["event"] != "VALIDATION_ONLY_POST_MATCH" else None
        (out / "packets" / f"{fx['match_id']}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        rendered.append(render_match(p))
    head = [f"# Günlük veri özeti — {day}", "",
            f"{len(fxs)} maç · ligler: {', '.join(sorted({f['competition'] for f in fxs})) or '—'} · oran bölgesi: {ODDS_GEO} · "
            f"oluşturuldu {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
            "Bu dosya yalnızca kanıttır; karar içermez. Marjsız olasılıklar bahisçi başına power yöntemiyle hesaplanıp medyanı alınmıştır. "
            "Model satırları kabadır ve piyasaya karşı doğrulanmamıştır. Eksik veri uydurulmaz, 'Eksik veri' satırında listelenir.", ""]
    (out / "OZET.md").write_text("\n".join(head + ["\n\n".join(rendered) or "_Bu tarihte hedef liglerde maç yok._"]) + "\n", encoding="utf-8")
    print(f"OK {len(fxs)} matches -> {out / 'OZET.md'}")


# ---------------------------------------------------------------- settle + CLV
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, rec: dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def outcome(market: str, selection: str, hg: int, ag: int) -> tuple[str, float]:
    """(WIN/LOSE/PUSH, return multiplier factor) for the supported markets."""
    sel = selection.upper()
    if market.upper() in ("1X2", "MONEYLINE"):
        res = "HOME" if hg > ag else "AWAY" if ag > hg else "DRAW"
        return ("WIN" if sel == res else "LOSE"), 0
    if sel.startswith(("OVER_", "UNDER_")):
        side, _, ln = sel.partition("_"); line = float(ln); goals = hg + ag
        if goals == line:
            return "PUSH", 0
        return ("WIN" if (goals > line) == (side == "OVER") else "LOSE"), 0
    if sel in ("HOME_DNB", "AWAY_DNB"):
        if hg == ag:
            return "PUSH", 0
        return ("WIN" if (hg > ag) == (sel == "HOME_DNB") else "LOSE"), 0
    raise ValueError(f"unsupported market/selection: {market} {selection}")


def cmd_settle(day: str):
    out = ROOT / "daily" / day
    fx_path = out / "fixtures.json"
    if not fx_path.exists():
        print(f"no fixtures for {day}"); return
    fxs = {f["match_id"]: f for f in json.loads(fx_path.read_text(encoding="utf-8"))}
    fs = FlashscoreClient()
    r = fs.matches("football", day)
    if not r.ok:
        raise RuntimeError(f"FLASHSCORE_MATCH_LIST_FAILED: {r.error}")
    rows = {str(m.get("id")): m for g in (r.data or {}).get("competitions") or [] for m in g.get("matches") or []}
    closing = {}
    for mid, fx in fxs.items():
        m = rows.get(mid) or {}
        rec = {"match_id": mid, "home": fx["home"], "away": fx["away"], "status": m.get("status"),
               "home_score": m.get("home_score"), "away_score": m.get("away_score")}
        if m.get("status") == "finished":
            o = fs.odds(mid, geo=ODDS_GEO); time.sleep(0.3)
            q = normalize_decimal_quotes(o.data, "flashscore") if o.ok else []
            s = market_summary(q)
            rec.update({"closing_basis": "flashscore post-match last pre-kickoff price", "closing_summary": s,
                        "closing_ok": bool(s.get("1x2"))})
        else:
            rec["closing_ok"] = False
        closing[mid] = rec
    (out / "closing.json").write_text(json.dumps(closing, ensure_ascii=False, indent=1), encoding="utf-8")
    # settle recorded decisions for these matches
    done = {(s["decision_id"]) for s in read_jsonl(ROOT / "decisions" / "settlements.jsonl")}
    n = 0
    for d in read_jsonl(ROOT / "decisions" / "decisions.jsonl"):
        if d["match_id"] not in closing or d["decision_id"] in done:
            continue
        c = closing[d["match_id"]]
        if c.get("status") != "finished" or c.get("home_score") is None:
            continue
        res, _ = outcome(d["market"], d["selection"], int(c["home_score"]), int(c["away_score"]))
        stake = float(d.get("stake") or 1.0)
        pnl = 0.0 if d["decision"] != "PLAY" else (stake * (d["price"] - 1) if res == "WIN" else 0.0 if res == "PUSH" else -stake)
        cfp = market_fair_probability(c.get("closing_summary") or {}, d["selection"]) if c.get("closing_ok") else None
        append_jsonl(ROOT / "decisions" / "settlements.jsonl", {
            "decision_id": d["decision_id"], "match_id": d["match_id"], "decision": d["decision"],
            "market": d["market"], "selection": d["selection"], "price": d["price"], "stake": stake,
            "score": f"{c['home_score']}-{c['away_score']}", "result": res, "pnl_units": round(pnl, 4),
            "closing_fair_probability": cfp, "clv": closing_line_value(d["price"], cfp),
            "settled_at": datetime.now(timezone.utc).isoformat()})
        n += 1
    print(f"settled {day}: {sum(1 for c in closing.values() if c.get('status') == 'finished')} finished, "
          f"{sum(1 for c in closing.values() if c.get('closing_ok'))} with closing prices, {n} decisions settled")


def cmd_record(a):
    fx = None
    for p in sorted((ROOT / "daily").glob("*/fixtures.json")):
        fx = next((f for f in json.loads(p.read_text(encoding="utf-8")) if f["match_id"] == a.match_id), fx)
    if not fx:
        raise SystemExit("match_id not found in any daily/*/fixtures.json — run scan first")
    kickoff = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if now >= kickoff:
        raise SystemExit(f"REFUSED: kickoff {kickoff.isoformat()} has passed — decisions must be recorded before kickoff")
    if a.decision == "PLAY" and not a.price:
        raise SystemExit("PLAY needs --price")
    rec = {"decision_id": f"{a.match_id}-{now:%Y%m%dT%H%M%S}", "match_id": a.match_id,
           "home": fx["home"], "away": fx["away"], "kickoff": fx["kickoff"], "decision": a.decision,
           "market": a.market, "selection": a.selection.upper(), "price": a.price, "bookmaker": a.bookmaker,
           "stake": a.stake, "decided_by": a.decided_by, "note": a.note, "recorded_at": now.isoformat(),
           "minutes_before_kickoff": round((kickoff - now).total_seconds() / 60, 1)}
    append_jsonl(ROOT / "decisions" / "decisions.jsonl", rec)
    print(json.dumps(rec, ensure_ascii=False))


def cmd_report():
    S = [s for s in read_jsonl(ROOT / "decisions" / "settlements.jsonl")]
    plays = [s for s in S if s["decision"] == "PLAY"]
    pnl = [s["pnl_units"] for s in plays]
    clv = [s["clv"] for s in plays if s.get("clv") is not None]
    cum = peak = dd = 0.0
    for x in pnl:
        cum += x; peak = max(peak, cum); dd = max(dd, peak - cum)
    stake = sum(float(s.get("stake") or 1) for s in plays)
    L = ["# Karar defteri raporu", "", f"Oluşturuldu: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
         "| ölçüt | değer |", "|---|---|",
         f"| kapanan karar | {len(S)} (PLAY {len(plays)} · WATCH {sum(s['decision'] == 'WATCH' for s in S)} · PASS {sum(s['decision'] == 'PASS' for s in S)}) |",
         f"| PLAY isabet | {sum(s['result'] == 'WIN' for s in plays)}/{len(plays)} |",
         f"| kâr (birim) | {sum(pnl):+.2f} |",
         f"| ROI | {(100 * sum(pnl) / stake) if stake else 0:+.2f}% |",
         f"| ortalama CLV | {(100 * sum(clv) / len(clv)) if clv else float('nan'):+.2f}% ({len(clv)} bahiste kapanış var) |",
         f"| kapanışı yenen bahis | {sum(c > 0 for c in clv)}/{len(clv)} |",
         f"| en büyük düşüş (birim) | {dd:.2f} |", "",
         "CLV = alınan oran × kapanıştaki marjsız olasılık − 1. 50 PLAY'den önce ROI şanstan ayırt edilemez; CLV daha erken bilgi verir."]
    (ROOT / "decisions").mkdir(exist_ok=True)
    (ROOT / "decisions" / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--date", default=date.today().isoformat()); s.add_argument("--limit", type=int)
    s.add_argument("--include-finished", action="store_true", help="validation only: also build packets for finished matches")
    t = sub.add_parser("settle"); t.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat())
    r = sub.add_parser("record")
    r.add_argument("--match-id", required=True); r.add_argument("--decision", choices=["PLAY", "WATCH", "PASS"], required=True)
    r.add_argument("--market", default="1X2"); r.add_argument("--selection", default="")
    r.add_argument("--price", type=float); r.add_argument("--bookmaker"); r.add_argument("--stake", type=float, default=1.0)
    r.add_argument("--decided-by", default="ChatGPT"); r.add_argument("--note", default="")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "scan":
        cmd_scan(a.date, a.limit, a.include_finished)
    elif a.cmd == "settle":
        cmd_settle(a.date)
    elif a.cmd == "record":
        cmd_record(a)
    else:
        cmd_report()


if __name__ == "__main__":
    main()
