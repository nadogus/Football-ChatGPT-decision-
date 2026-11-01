"""Live Flashscore XI verification against a completed Premier League match."""
from __future__ import annotations
import json
from data_adapters import FlashscoreClient
from fixture_resolver import resolve_flashscore

MATCH={
    "home":"Liverpool",
    "away":"Brighton",
    "kickoff":"2026-10-25T14:00:00+00:00",
    "competition":"English Premier League",
}

resolved=resolve_flashscore(MATCH)
report={"match":MATCH,"resolved":resolved}
if not resolved.get("resolved"):
    report["status"]="FAIL_RESOLVE"
else:
    match_id=resolved["id"]
    r=FlashscoreClient().lineups(match_id)
    report["lineups_ok"]=r.ok
    report["lineups_error"]=r.error
    report["lineups_payload"]=r.data
    report["status"]="RAW_LINEUPS_CAPTURED" if r.ok and r.data else "FAIL_LINEUPS"
with open("LIVE_XI_PROBE.json","w",encoding="utf-8") as f:
    json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False,indent=2))
if report["status"]!="RAW_LINEUPS_CAPTURED":
    raise SystemExit(report["status"])
