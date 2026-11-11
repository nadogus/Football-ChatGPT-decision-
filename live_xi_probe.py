"""Live Flashscore XI verification against a recently completed Premier League match.

The scraper only lists matches within ±7 days, so the probe looks back day by day
instead of using a hard-coded old fixture (that was why this CI step kept failing)."""
from __future__ import annotations
import json
from datetime import date, timedelta
from data_adapters import FlashscoreClient
from source_pipeline import parse_flashscore_xi

fs = FlashscoreClient(); report = {"status": "NO_RECENT_EPL_MATCH"}
for n in range(1, 8):
    d = (date.today() - timedelta(days=n)).isoformat(); r = fs.matches("football", d)
    if not r.ok: continue
    for g in (r.data or {}).get("competitions") or []:
        c = g.get("competition") or {}
        if (c.get("category"), c.get("name")) != ("England", "Premier League"): continue
        m = next((x for x in g.get("matches") or [] if x.get("status") == "finished"), None)
        if not m: continue
        lu = fs.lineups(m["id"]); parsed = parse_flashscore_xi(lu.data) if lu.ok else {"home_starters": [], "away_starters": []}
        good = lu.ok and len(parsed["home_starters"]) == 11 and len(parsed["away_starters"]) == 11
        report = {"date": d, "match": f"{m['home']['name']} - {m['away']['name']}", "match_id": m["id"], "parsed_xi": parsed,
                  "status": "OFFICIAL_XI_11_PLUS_11_VERIFIED" if good else "FAIL_LINEUPS"}
        break
    if report["status"] != "NO_RECENT_EPL_MATCH": break
with open("LIVE_XI_PROBE.json", "w", encoding="utf-8") as f: json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
if report["status"] == "FAIL_LINEUPS": raise SystemExit(report["status"])
