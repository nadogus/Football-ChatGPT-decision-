"""One-off probe: FotMob match details — lineups and unavailable players."""
import json, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

s, b = get("https://www.fotmob.com/api/data/matches?date=20261112")
d = json.loads(b); ids = []
for lg in d.get("leagues", []):
    for m in lg.get("matches", [])[:1]:
        ids.append((lg.get("name"), m["id"], m["home"]["name"], m["away"]["name"]))
print("PROBE leagues on 2026-11-12:", len(d.get("leagues", [])))
for name, mid, h, a in ids[:3]:
    s, b = get(f"https://www.fotmob.com/api/data/matchDetails?matchId={mid}")
    print(f"PROBE matchDetails {name} {h}-{a} id={mid}: status={s} len={len(b)}")
    if s != 200 or not b.startswith("{"):
        print("PROBE head", json.dumps(b[:200])); continue
    j = json.loads(b); c = j.get("content") or {}
    print("PROBE content keys:", sorted(c.keys()))
    lu = c.get("lineup") or {}
    print("PROBE lineup keys:", sorted(lu.keys()) if isinstance(lu, dict) else type(lu).__name__, "| lineupType:", lu.get("lineupType") if isinstance(lu, dict) else None)
    for side in ("homeTeam", "awayTeam"):
        t = lu.get(side) or {}
        un = t.get("unavailable") or []
        print(f"PROBE {side} {t.get('name')}: starters={len(t.get('starters') or [])} unavailable={len(un)} sample={json.dumps(un[:2])[:350]}")
# finished top-league match (Napoli-Lazio, 2026-11-08)
s, b = get("https://www.fotmob.com/api/data/matches?date=20261108")
for lg in json.loads(b).get("leagues", []):
    for m in lg.get("matches", []):
        if "Napoli" in m["home"]["name"]:
            s2, b2 = get(f"https://www.fotmob.com/api/data/matchDetails?matchId={m['id']}")
            lu = (json.loads(b2).get("content") or {}).get("lineup") or {} if s2 == 200 else {}
            for side in ("homeTeam", "awayTeam"):
                t = lu.get(side) or {}
                print(f"PROBE NAPOLI-LAZIO {side} {t.get('name')}: starters={len(t.get('starters') or [])} unavailable={json.dumps([(u.get('name'), (u.get('unavailability') or {}).get('type'), (u.get('unavailability') or {}).get('expectedReturn')) for u in (t.get('unavailable') or [])])[:500]}")
