"""One-shot real-provider probe for Liverpool v Arsenal, 2026-11-01.
Diagnostic only; never makes a betting decision.
"""
import json
from fixture_resolver import resolve_provider_ids
from evidence_collector import collect_match_evidence_auto

match={"home":"Liverpool","away":"Arsenal","kickoff":"2026-11-01T16:30:00+00:00","competition":"Premier League"}

# Public provider contexts. Optional/private providers remain explicit gaps.
resolution=resolve_provider_ids(
    match=match,
    espn_league_slug="eng.1",
    fotmob_league_id=47,
    pinnacle_league_id=None,
    date_yyyymmdd="20261101",
    odds_league="premier-league",
)
print("REAL_PROBE_RESOLUTION="+json.dumps(resolution,sort_keys=True,default=str))

collection=collect_match_evidence_auto(
    match=match,
    espn_league_slug="eng.1",
    fotmob_league_id=47,
    pinnacle_league_id=None,
    date_yyyymmdd="20261101",
    odds_league="premier-league",
)
summary={
    "provider_ids":collection.get("provider_ids",{}),
    "fixture_resolution":collection.get("resolution",{}),
    "collection_status":collection.get("collection_status",{}),
}
print("REAL_PROBE_COLLECTION="+json.dumps(summary,sort_keys=True,default=str))
