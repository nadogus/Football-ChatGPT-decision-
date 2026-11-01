"""Live provider probe for the known Liverpool-Arsenal fixture.
Evidence-only: validates provider reachability/resolution, never betting decisions.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from fixture_resolver import resolve_flashscore, resolve_pinnacle

MATCH={
    "home":"Liverpool",
    "away":"Arsenal",
    "kickoff":"2026-11-01T16:30:00+00:00",
    "competition":"English Premier League",
}
PREMIER_LEAGUE_PINNACLE_ID=1980

flash=resolve_flashscore(MATCH)
pinnacle=resolve_pinnacle(MATCH,PREMIER_LEAGUE_PINNACLE_ID)

report={
    "generated_at":datetime.now(timezone.utc).isoformat(),
    "match":MATCH,
    "flashscore":flash,
    "pinnacle":pinnacle,
}
with open("LIVE_PROVIDER_PROBE.json","w",encoding="utf-8") as f:
    json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False,indent=2))
if not flash.get("resolved"):raise SystemExit("FLASHSCORE_FIXTURE_NOT_RESOLVED")
if not pinnacle.get("resolved"):raise SystemExit("PINNACLE_FIXTURE_NOT_RESOLVED")
