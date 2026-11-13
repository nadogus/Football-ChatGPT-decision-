"""Canlı maç izleyici: FotMob'dan canlı istatistik çeker, kaydeder, filtreye takılan maçı Slack'e bildirir.

Karar VERMEZ. Uyarı sadece "Claude'a sor" demektir; kararı Claude verir (bkz. CANLI_KARAR.md).

Kaynak: FotMob'un kendi sitesinin kullandığı resmi olmayan uç nokta (anahtar yok). Değişebilir; her hata
kapalı başarısız olur ve sebebi kaydedilir. Eksik istatistik uydurulmaz, None kalır.

Çıktılar (daily/<tarih>/live/):
  <fotmob_id>.jsonl   her çalıştırmada bir anlık görüntü (trend için)
  index.json          izlenen maçlar: fotmob_id, takımlar, son dakika/skor
  state.json          çözülen FotMob id'leri ve gönderilmiş uyarılar (aynı uyarı iki kez gitmez)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fotmob_source import FotMobClient

ROOT = Path(__file__).resolve().parent
WATCH_BEFORE_MIN = 2      # başlama saatinden 2 dk önce izlemeye başla
WATCH_AFTER_MIN = 130     # başlamadan 130 dk sonrasına kadar

# İstatistik eşleme: FotMob anahtar(lar)ı veya başlık(lar)ı (küçük harf)
STAT_KEYS: dict[str, tuple[str, ...]] = {
    "xg": ("expected_goals", "expected goals (xg)", "expected goals"),
    "xgot": ("expected_goals_on_target", "xg on target (xgot)", "expected goals on target"),
    "box_touches": ("touches_opp_box", "touches in opposition box"),
    "shots": ("total_shots", "total shots"),
    "shots_on_target": ("shotsontarget", "shots on target"),
    "big_chances": ("big_chance", "big chances"),
    "big_chances_missed": ("big_chance_missed_title", "big chances missed"),
    "possession": ("ballpossesion", "ball possession"),
    "corners": ("corners",),
    "red_cards": ("red_cards", "red cards"),
}

# Filtre eşikleri (uyarı içindir, karar değildir)
MIN_MINUTE, MAX_MINUTE = 15, 85
PRESSURE_XG_GAP = 0.8      # xG farkı en az bu kadar ve baskın taraf önde değil
OPEN_GAME_XG = 2.0         # toplam xG en az bu kadar ama en fazla 1 gol
OPEN_GAME_MAX_MINUTE = 75
SURGE_XG_15 = 0.7          # bir taraf son ~15 dakikada en az bu kadar xG üretti


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.match(r"\s*(-?\d+(?:[.,]\d+)?)", v)
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def extract_stats(details: dict[str, Any]) -> dict[str, list[float | None] | None]:
    """{'xg': [home, away], ...}; bulunamayan istatistik None."""
    periods = (((details or {}).get("content") or {}).get("stats") or {}).get("Periods") or {}
    groups = ((periods.get("All") or {}).get("stats")) or []
    found: dict[str, list[float | None]] = {}
    for g in groups:
        for s in (g or {}).get("stats") or []:
            key = str(s.get("key") or "").lower()
            title = str(s.get("title") or "").lower()
            vals = s.get("stats")
            if not isinstance(vals, list) or len(vals) != 2:
                continue
            for name, aliases in STAT_KEYS.items():
                if name not in found and (key in aliases or title in aliases):
                    found[name] = [_num(vals[0]), _num(vals[1])]
    return {name: found.get(name) for name in STAT_KEYS}


def extract_header(details: dict[str, Any]) -> dict[str, Any]:
    h = (details or {}).get("header") or {}
    st = h.get("status") or {}
    teams = h.get("teams") or [{}, {}]
    live = st.get("liveTime") or {}
    minute = _num(str(live.get("short") or "").replace("’", "").replace("'", ""))
    if minute is None and st.get("halfs", {}).get("firstHalfEnded") and not st.get("halfs", {}).get("secondHalfStarted"):
        minute = 45.0
    return {
        "home": (teams[0] or {}).get("name"), "away": (teams[1] or {}).get("name"),
        "score": [(teams[0] or {}).get("score"), (teams[1] or {}).get("score")],
        "minute": minute, "minute_text": live.get("short") or ((st.get("reason") or {}).get("short")),
        "started": bool(st.get("started")), "finished": bool(st.get("finished")),
    }


def snapshot(details: dict[str, Any], now: datetime) -> dict[str, Any]:
    snap = {"t": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **extract_header(details), "stats": extract_stats(details)}
    snap["missing"] = [k for k, v in snap["stats"].items() if v is None]
    return snap


def _side_name(snap, i):
    return snap["home"] if i == 0 else snap["away"]


def triggers(snap: dict[str, Any], history: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """[(uyarı_anahtarı, açıklama)]. Anahtar maç başına bir kez gönderilir."""
    out: list[tuple[str, str]] = []
    m = snap.get("minute")
    if not snap.get("started") or snap.get("finished") or m is None or not (MIN_MINUTE <= m <= MAX_MINUTE):
        return out
    s = snap["stats"]
    sc = [x if isinstance(x, int) else _num(x) for x in snap["score"]]
    xg = s.get("xg")
    if xg and None not in xg and None not in sc:
        for i in (0, 1):
            gap = xg[i] - xg[1 - i]
            if gap >= PRESSURE_XG_GAP and sc[i] <= sc[1 - i]:
                out.append((f"baski_{i}", f"{_side_name(snap, i)} baskın (xG {xg[i]:.2f}–{xg[1 - i]:.2f}) ama önde değil"))
        if sum(xg) >= OPEN_GAME_XG and sum(sc) <= 1 and m <= OPEN_GAME_MAX_MINUTE:
            out.append(("acik_mac", f"Açık maç: toplam xG {sum(xg):.2f}, skor {sc[0]}-{sc[1]}"))
        # son ~15 dakikadaki xG artışı
        past = [h for h in history if h.get("minute") is not None and m - 20 <= h["minute"] <= m - 12
                and (h.get("stats") or {}).get("xg") and None not in h["stats"]["xg"]]
        if past:
            base = past[0]["stats"]["xg"]
            for i in (0, 1):
                d = xg[i] - base[i]
                if d >= SURGE_XG_15:
                    bucket = int(m // 15)
                    out.append((f"atak_{i}_{bucket}", f"{_side_name(snap, i)} son ~15 dk'da +{d:.2f} xG üretti"))
    rc = s.get("red_cards")
    if rc and None not in rc:
        for i in (0, 1):
            if rc[i] and rc[i] > 0:
                out.append((f"kirmizi_{i}_{int(rc[i])}", f"{_side_name(snap, i)} kırmızı kart gördü ({int(rc[i])})"))
    return out


def fmt_pair(v, fmt="{:.2f}"):
    if not v or None in v:
        return "—"
    return f"{fmt.format(v[0])}–{fmt.format(v[1])}"


def alert_text(fid, snap, reasons) -> str:
    s = snap["stats"]
    lines = [f"⚡ *Canlı uyarı* — {snap['home']} {snap['score'][0]}-{snap['score'][1]} {snap['away']} ({snap.get('minute_text') or snap.get('minute')})"]
    lines += [f"• {r}" for r in reasons]
    lines.append(f"xG {fmt_pair(s['xg'])} · xGOT {fmt_pair(s['xgot'])} · ceza sahası topla buluşma {fmt_pair(s['box_touches'], '{:.0f}')} · "
                 f"isabetli şut {fmt_pair(s['shots_on_target'], '{:.0f}')}")
    if snap["missing"]:
        lines.append(f"Eksik veri: {', '.join(snap['missing'])}")
    lines.append(f"Karar için Claude'a yaz: `canlı bak {fid}`")
    lines.append("_Uyarıdır, karar değildir._")
    return "\n".join(lines)


def notify(text: str) -> list[str]:
    sent = []
    hook = os.getenv("SLACK_LIVE_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK_URL")
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
                                                          {"Title": "Canli uyari"}), timeout=20)
            sent.append("ntfy")
        except Exception as e:
            print("ntfy notify failed:", type(e).__name__)
    return sent


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def live_fixtures(now: datetime, root: Path = ROOT) -> list[dict[str, Any]]:
    out = []
    for day in {(now - timedelta(days=1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")}:
        for f in _load(root / "daily" / day / "fixtures.json", []):
            try:
                k = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
            except Exception:
                continue
            mins = (now - k).total_seconds() / 60
            if -WATCH_BEFORE_MIN <= mins <= WATCH_AFTER_MIN:
                out.append(f)
    return out


def run(now: datetime | None = None, client: FotMobClient | None = None, extra_ids: list[str] | None = None,
        root: Path = ROOT, send=notify) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    client = client or FotMobClient()
    outdir = root / "daily" / now.strftime("%Y-%m-%d") / "live"
    outdir.mkdir(parents=True, exist_ok=True)
    state = _load(outdir / "state.json", {"resolved": {}, "alerts": {}, "errors": []})
    index = _load(outdir / "index.json", {})

    targets: dict[str, dict[str, Any]] = {}
    for f in live_fixtures(now, root):
        key = str(f.get("match_id") or f"{f['home']}|{f['away']}")
        fid = state["resolved"].get(key)
        if not fid:
            r = client.resolve(f)
            fid = r.get("id") if r.get("resolved", True) and r.get("id") else None
            if not fid:
                state["errors"].append({"t": now.isoformat(), "match": key, "reason": r.get("reason") or "FotMob eşleşmedi"})
                continue
            state["resolved"][key] = str(fid)
        targets[str(fid)] = {"flashscore_id": f.get("match_id"), "competition": f.get("competition")}
    for fid in extra_ids or []:
        targets.setdefault(str(fid), {"flashscore_id": None, "competition": None, "manual": True})

    report = {"watched": 0, "alerts": 0}
    for fid, meta in targets.items():
        try:
            snap = snapshot(client.details(fid), now)
        except Exception as e:
            state["errors"].append({"t": now.isoformat(), "fotmob_id": fid, "reason": f"{type(e).__name__}: {e}"})
            continue
        path = outdir / f"{fid}.jsonl"
        history = [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        if history and history[-1].get("finished") and snap["finished"]:
            continue
        with path.open("a") as fh:
            fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
        report["watched"] += 1
        index[fid] = {**meta, "home": snap["home"], "away": snap["away"], "score": snap["score"],
                      "minute": snap["minute_text"] or snap["minute"], "finished": snap["finished"], "updated": snap["t"]}
        sent_keys = set(state["alerts"].get(fid, []))
        new = [(k, r) for k, r in triggers(snap, history) if k not in sent_keys]
        if new:
            send(alert_text(fid, snap, [r for _, r in new]))
            state["alerts"][fid] = sorted(sent_keys | {k for k, _ in new})
            report["alerts"] += 1
    state["errors"] = state["errors"][-50:]
    (outdir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))
    (outdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fotmob-id", action="append", default=[], help="Lig listesinde olmayan bir maçı da izle")
    a = ap.parse_args()
    ids = a.fotmob_id + [x for x in (os.getenv("LIVE_EXTRA_IDS") or "").replace(",", " ").split() if x]
    print(json.dumps(run(extra_ids=ids), ensure_ascii=False))


if __name__ == "__main__":
    main()
