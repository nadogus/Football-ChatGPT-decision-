"""Automated evidence collection. Never assigns PLAY/WATCH/PASS."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from data_adapters import AdapterResult, ESPNLineupClient, FlashscoreClient, PinnaclePrematchClient, normalize_decimal_quotes
COLLECTOR_VERSION="EVIDENCE_COLLECTOR_V1.2"
def _result(r:AdapterResult)->dict[str,Any]:return {"source":r.source,"ok":r.ok,"observed_at":r.observed_at,"data":r.data,"error":r.error}
def _gap(source,reason):return {"source":source,"ok":False,"observed_at":datetime.now(timezone.utc).isoformat(),"data":{},"error":reason}
def collect_match_evidence(*,match:dict[str,Any],provider_ids:dict[str,Any]|None=None,pinnacle_league_id:int|None=None,resolution:dict[str,Any]|None=None,**_ignored)->dict[str,Any]:
    ids=provider_ids or {};evidence=[];quotes=[];lineup_evidence=[]
    if ids.get("espn_league_slug") and ids.get("espn_event_id"):
        r=ESPNLineupClient().summary(str(ids["espn_league_slug"]),str(ids["espn_event_id"]));evidence.append(_result(r))
        if r.ok:lineup_evidence.append({"source":"espn","starter_ids":ESPNLineupClient.lineup_ids(r.data),"observed_at":r.observed_at})
    else:evidence.append(_gap("espn","ESPN_PROVIDER_IDS_MISSING"))
    if ids.get("flashscore_match_id"):
        fs=FlashscoreClient()
        for label,r in (("details",fs.details(str(ids["flashscore_match_id"]))),("lineups",fs.lineups(str(ids["flashscore_match_id"]))),("odds",fs.odds(str(ids["flashscore_match_id"])))):
            d=_result(r);d["kind"]=label;evidence.append(d)
            if label=="odds" and r.ok:quotes.extend(normalize_decimal_quotes(r.data,"flashscore"))
    else:evidence.append(_gap("flashscore","FLASHSCORE_MATCH_ID_MISSING"))
    effective_pinnacle_league_id=pinnacle_league_id or ids.get("pinnacle_league_id")
    if effective_pinnacle_league_id is not None:
        r=PinnaclePrematchClient().odds(int(effective_pinnacle_league_id),ids.get("pinnacle_matchup_id"));evidence.append(_result(r))
        if r.ok:quotes.extend(normalize_decimal_quotes(r.data,"pinnacle"))
    else:evidence.append(_gap("pinnacle","PINNACLE_LEAGUE_ID_MISSING"))
    gaps=[{"source":x["source"],"reason":x.get("error") or "UNKNOWN"} for x in evidence if not x.get("ok")];successful=[x["source"] for x in evidence if x.get("ok")]
    return {"collector_version":COLLECTOR_VERSION,"collected_at":datetime.now(timezone.utc).isoformat(),"match":match,"provider_ids":ids,"resolution":resolution or {},"source_results":evidence,"lineup_evidence":lineup_evidence,"odds_payload":{"primary_source":"flashscore+pinnacle","observed_at":datetime.now(timezone.utc).isoformat(),"quotes":quotes},"collection_status":{"successful_sources":sorted(set(successful)),"gaps":gaps,"quote_count":len(quotes),"lineup_source_count":len(lineup_evidence)}}
def collect_match_evidence_auto(*,match:dict[str,Any],espn_league_slug:str|None=None,pinnacle_league_id:int|None=None,**_ignored)->dict[str,Any]:
    from fixture_resolver import resolve_provider_ids
    resolution=resolve_provider_ids(match=match,espn_league_slug=espn_league_slug,pinnacle_league_id=pinnacle_league_id)
    effective_id=pinnacle_league_id or resolution.get("resolved_ids",{}).get("pinnacle_league_id")
    return collect_match_evidence(match=match,provider_ids=resolution.get("resolved_ids",{}),pinnacle_league_id=effective_id,resolution=resolution)
def packet_inputs(collection):
    source_payloads=[{"source":x["source"],"observed_at":x.get("observed_at"),"data":x.get("data",{})} for x in collection.get("source_results",[]) if x.get("ok")]
    context={"collector_version":collection.get("collector_version"),"provider_ids":collection.get("provider_ids",{}),"fixture_resolution":collection.get("resolution",{}),"collection_status":collection.get("collection_status",{}),"lineup_evidence":collection.get("lineup_evidence",[])}
    return {"source_payloads":source_payloads,"odds_payload":collection.get("odds_payload",{}),"context":context}
