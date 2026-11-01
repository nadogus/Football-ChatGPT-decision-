"""Live LaLiga Pinnacle capability probe.

Validates that LaLiga resolves to Pinnacle and that the live guest feed exposes at
least one future LaLiga matchup. Evidence only; no production decision.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json

from competition_resolver import FlashscoreCompetitionResolver, resolve_pinnacle_league
from data_adapters import PinnaclePrematchClient

def main():
    now=datetime.now(timezone.utc)
    profile=FlashscoreCompetitionResolver().profile("Barcelona","LaLiga",as_of=now)
    league=resolve_pinnacle_league(profile) if profile else {"resolved":False,"reason":"COMPETITION_PROFILE_UNRESOLVED"}
    rows=[]
    if league.get("resolved"):
        out=PinnaclePrematchClient().odds(int(league["league_id"]),None)
        if out.ok:
            rows=out.data
        else:
            league={**league,"feed_error":out.error}
    event=None
    seen=set()
    for row in rows:
        eid=str(row.get("event_id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        event={"event_id":eid,"home":row.get("home"),"away":row.get("away"),"start_time":row.get("start_time")}
        break
    report={
        "generated_at":now.isoformat(),
        "test_type":"LALIGA_PINNACLE_LIVE_CAPABILITY",
        "competition_profile":profile,
        "pinnacle_league_resolution":league,
        "future_quote_count":len(rows),
        "sample_future_matchup":event,
        "decision_authority":"CHATGPT_ONLY",
        "production_decision":None,
        "status":"LALIGA_PINNACLE_READY" if league.get("resolved") and event else "FAIL_CLOSED_LALIGA_PINNACLE_UNAVAILABLE",
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    with open("LALIGA_PINNACLE_LIVE.json","w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    if report["status"]!="LALIGA_PINNACLE_READY":
        raise SystemExit(1)

if __name__=="__main__":
    main()
