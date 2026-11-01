"""Evidence-only source orchestration.
Collects match, XI, availability and odds evidence. Never returns PLAY/WATCH/PASS.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from data_adapters import TransfermarktV4Client, ESPNLineupClient, FotMobLineupClient, FlashscoreClient, PinnaclePrematchClient, OddsHarvesterClient, normalize_decimal_quotes
from public_sources import SofaScoreClient

SOURCE_ROLES={"pinnacle":"PRIMARY_PREMATCH_ODDS","flashscore":"PRIMARY_MATCH_XI_BACKBONE","espn":"XI_VALIDATOR","fotmob":"XI_VALIDATOR","sofascore":"SECONDARY_VALIDATOR","transfermarkt":"AVAILABILITY_ENRICHMENT","oddsharvester":"ODDS_FALLBACK"}

def collect_match_backbone(*,match_id:str|None=None,date:str|None=None):
    fs=FlashscoreClient(); r=fs.details(match_id) if match_id else fs.matches("football",date)
    return {"source":"flashscore","role":SOURCE_ROLES["flashscore"],"data":r.data if r.ok else {},"errors":[] if r.ok else [r.error],"fail_closed":not r.ok,"observed_at":r.observed_at}

def _sofa_lineup_ids(payload:dict[str,Any])->list[str]:
    ids=[]
    for side in ("home","away"):
        block=payload.get(side,{})
        players=block.get("players",[]) if isinstance(block,dict) else []
        for row in players:
            if not isinstance(row,dict): continue
            starter=row.get("starter") is True or row.get("substitute") is False
            p=row.get("player",{}) if isinstance(row.get("player"),dict) else row
            if starter and p.get("id") is not None: ids.append(str(p["id"]))
    return list(dict.fromkeys(ids))

def _starter_count(payload:Any)->int:
    """Conservative generic count of explicitly marked starters only."""
    count=0
    def walk(x):
        nonlocal count
        if isinstance(x,dict):
            marker=x.get("starter") is True or x.get("isStarter") is True or x.get("starting") is True
            # substitute=False alone is accepted only when player identity is present.
            marker=marker or (x.get("substitute") is False and any(k in x for k in ("player","playerId","id","name")))
            if marker: count+=1
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(payload)
    return count

def _confirmed_flag(payload:Any)->bool:
    """Accept explicit provider confirmation markers; never infer confirmed XI from non-empty payload."""
    found=False
    def walk(x):
        nonlocal found
        if found:return
        if isinstance(x,dict):
            for k,v in x.items():
                key=str(k).lower().replace("_","")
                if key in {"confirmed","isconfirmed","lineupsconfirmed","official","isofficial"} and v is True: found=True;return
                if key in {"status","lineupstatus","type"} and isinstance(v,str) and v.lower() in {"confirmed","official","starting","final"}: found=True;return
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(payload);return found

def verify_official_xi(primary_payload:Any, validator_lineups:list[list[str]]|None=None)->dict[str,Any]:
    """Fail closed: a non-empty lineup response is NOT sufficient for POST_XI."""
    validator_lineups=validator_lineups or []
    starter_count=_starter_count(primary_payload)
    explicit=_confirmed_flag(primary_payload)
    validators=sum(len(set(map(str,x)))>=11 for x in validator_lineups if x)
    # Require a plausible full starting set (22 total) AND either explicit provider confirmation or independent validator.
    verified=starter_count>=22 and (explicit or validators>=1)
    return {"verified":verified,"starter_count":starter_count,"explicit_confirmation":explicit,"independent_validators":validators,
            "reason":"CONFIRMED_OFFICIAL_XI" if verified else "OFFICIAL_XI_NOT_STRONGLY_VERIFIED"}

def collect_xi(*,flashscore_match_id:str,sofascore_event_id:str|None=None,espn_league_slug:str|None=None,espn_event_id:str|None=None,fotmob_match_id:str|None=None):
    errors=[];fs=FlashscoreClient().lineups(flashscore_match_id);flash=fs.data if fs.ok else {}
    if not fs.ok:errors.append(f"flashscore:{fs.error}")
    sofa_payload={};sofa_ids=[]
    if sofascore_event_id:
        try: sofa_payload=SofaScoreClient().lineups(sofascore_event_id);sofa_ids=_sofa_lineup_ids(sofa_payload)
        except Exception as e:errors.append(f"sofascore:{type(e).__name__}:{e}")
    espn_ids=[]
    if espn_league_slug and espn_event_id:
        r=ESPNLineupClient().summary(espn_league_slug,espn_event_id)
        if r.ok:espn_ids=ESPNLineupClient.lineup_ids(r.data)
        else:errors.append(f"espn:{r.error}")
    fotmob_ids=[]
    if fotmob_match_id:
        r=FotMobLineupClient().match_details(fotmob_match_id)
        if r.ok:fotmob_ids=FotMobLineupClient.lineup_ids(r.data)
        else:errors.append(f"fotmob:{r.error}")
    proof=verify_official_xi(flash,[sofa_ids,espn_ids,fotmob_ids]) if fs.ok else {"verified":False,"starter_count":0,"explicit_confirmation":False,"independent_validators":0,"reason":"PRIMARY_XI_SOURCE_FAILED"}
    reliability=0.0 if not proof["verified"] else (0.90 if proof["independent_validators"]==1 else 0.95)
    return {"official_verified":proof["verified"],"verification":proof,"reliability":reliability,"primary_source":"flashscore","flashscore":flash,"sofascore":sofa_payload,"espn_ids":espn_ids,"fotmob_ids":fotmob_ids,"validator_count":proof["independent_validators"],"errors":errors,"fail_closed":not proof["verified"],"observed_at":datetime.now(timezone.utc).isoformat()}

def collect_availability(player_ids:list[str]):
    tm=TransfermarktV4Client();rows={};errors=[]
    for pid in player_ids:
        r=tm.availability(pid)
        if r.ok:rows[str(pid)]=r.data
        else:errors.append(f"{pid}:{r.error}")
    return {"source":"transfermarkt","players":rows,"errors":errors,"configured":bool(tm.base),"observed_at":datetime.now(timezone.utc).isoformat()}

def collect_odds(*,flashscore_match_id:str|None=None,pinnacle_league_id:int|None=None,pinnacle_matchup_id:int|None=None,date_yyyymmdd:str|None=None,league:str|None=None):
    errors=[];quotes=[];source=None
    if pinnacle_league_id is not None:
        r=PinnaclePrematchClient().odds(int(pinnacle_league_id),pinnacle_matchup_id)
        if r.ok and r.data:quotes=r.data;source="pinnacle"
        else:errors.append(f"pinnacle:{r.error or 'NO_QUOTES'}")
    if not quotes and flashscore_match_id:
        r=FlashscoreClient().odds(flashscore_match_id)
        if r.ok:
            q=normalize_decimal_quotes(r.data,"flashscore")
            if q:quotes=q;source="flashscore"
            else:errors.append("flashscore:NO_QUOTES")
        else:errors.append(f"flashscore:{r.error}")
    if not quotes and date_yyyymmdd:
        r=OddsHarvesterClient().upcoming(date_yyyymmdd,league=league)
        if r.ok:
            q=normalize_decimal_quotes(r.data,"oddsharvester")
            if q:quotes=q;source="oddsharvester"
            else:errors.append("oddsharvester:NO_QUOTES")
        else:errors.append(f"oddsharvester:{r.error}")
    return {"primary_source":source,"fallback_order":["pinnacle","flashscore","oddsharvester"],"quotes":quotes,"errors":errors,"fail_closed":not bool(quotes),"observed_at":datetime.now(timezone.utc).isoformat()}
