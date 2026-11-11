"""One-off probe: which injury/absence sources actually return data from GitHub Actions?"""
import json, urllib.request, urllib.parse
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"}

def get(url, headers=None):
    try:
        req = urllib.request.Request(url, headers={**UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, (e.read() or b"")[:300].decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def show(label, status, body):
    print(f"PROBE {label}: status={status} len={len(body or '')} head={json.dumps((body or '')[:220])}")

# --- ESPN: does the soccer summary carry injuries?
s, b = get("https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard?dates=20261108")
eid = None
try:
    for e in json.loads(b).get("events", []):
        if "Napoli" in e.get("name", ""): eid = e["id"]
except Exception: pass
s, b = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/summary?event={eid}")
try:
    d = json.loads(b); print("PROBE espn summary keys:", sorted(d.keys())); print("PROBE espn injuries:", json.dumps(d.get("injuries"))[:400])
except Exception as e: show("espn summary", s, b)

# --- Transfermarkt community API (MIT, felipeall/transfermarkt-api) public instance
for path in ("/clubs/search/Napoli", "/clubs/6195/players"):
    s, b = get("https://transfermarkt-api.fly.dev" + path); show("transfermarkt-api.fly.dev" + path, s, b)
# Transfermarkt site itself (club injuries page)
s, b = get("https://www.transfermarkt.com/ssc-neapel/sperrenundverletzungen/verein/6195")
show("transfermarkt.com injuries page", s, b[:200] if b else b)
print("PROBE transfermarkt page mentions injury table:", ("Verletzung" in (b or "")) or ("injury" in (b or "").lower()))

# --- FotMob web API
s, b = get("https://www.fotmob.com/api/matches?date=" + (date.today() + timedelta(days=1)).strftime("%Y%m%d"))
show("fotmob /api/matches", s, b)
s, b = get("https://www.fotmob.com/api/data/matches?date=" + (date.today() + timedelta(days=1)).strftime("%Y%m%d"))
show("fotmob /api/data/matches", s, b)
