"""Fail-closed fixture/provider ID resolution for supported providers."""
from __future__ import annotations
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
import re
from data_adapters import ESPNLineupClient, FlashscoreClient, PinnaclePrematchClient, _json
RESOLVER_VERSION="FIXTURE_RESOLVER_V1.1"
def _norm(s:str|None)->str:
    s=(s or "").lower();s=re.sub(r"\b(fc|cf|afc|sc|ac|club|football|futbol|soccer)\b"," ",s);s=re.sub(r"[^a-z0-9]+"," ",s);return " ".join(s.split())
def _team_score(a,b):
    aa,bb=_norm(a),_norm(b)
    if not aa or not bb:return 0.0
    return 1.0 if aa==bb else SequenceMatcher(None,aa,bb).ratio()
def _dt(value):
    if not value:return None
    try:
        x=datetime.fromisoformat(str(value).replace("Z","+00:00"));return (x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x).astimezone(timezone.utc)
    except Exception:return None
def _kickoff_score(target,candidate,tolerance_minutes=180):
    a,b=_dt(target),_dt(candidate)
    if not a or not b:return .5
    delta=abs((a-b).total_seconds())/60
    return 0.0 if delta>tolerance_minutes else max(0.0,1-delta/tolerance_minutes)
def fixture_score(match,home,away,kickoff):return round(.425*_team_score(match.get("home"),home)+.425*_team_score(match.get("away"),away)+.15*_kickoff_score(match.get("kickoff"),kickoff),6)
def _walk_events(x:Any)->list[dict[str,Any]]:
    out=[]
    if isinstance(x,dict):
        home=x.get("home");away=x.get("away")
        if isinstance(home,dict):home=home.get("name") or home.get("shortName")
        if isinstance(away,dict):away=away.get("name") or away.get("shortName")
        if not home or not away:
            comps=x.get("competitors")
            if isinstance(comps,list):
                for c in comps:
                    if not isinstance(c,dict):continue
                    team=c.get("team") if isinstance(c.get("team"),dict) else c;name=team.get("displayName") or team.get("name") or team.get("shortDisplayName");side=c.get("homeAway") or c.get("alignment")
                    if side=="home":home=name
                    elif side=="away":away=name
        if home and away:out.append({"id":x.get("id") or x.get("eventId") or x.get("matchId") or x.get("matchupId"),"home":home,"away":away,"kickoff":x.get("start_time") or x.get("startTime") or x.get("utcTime") or x.get("start") or x.get("date"),"raw":x})
        for v in x.values():out.extend(_walk_events(v))
    elif isinstance(x,list):
        for v in x:out.extend(_walk_events(v))
    return out
def best_fixture(match,candidates,threshold=.86,margin=.06):
    scored=[(fixture_score(match,c.get("home"),c.get("away"),c.get("kickoff")),c) for c in candidates if c.get("id")];scored.sort(key=lambda z:z[0],reverse=True)
    if not scored:return {"resolved":False,"reason":"NO_CANDIDATES"}
    top_s,top=scored[0];second=scored[1][0] if len(scored)>1 else 0.0
    if top_s<threshold:return {"resolved":False,"reason":"LOW_MATCH_SCORE","top_score":top_s}
    if len(scored)>1 and top_s-second<margin:return {"resolved":False,"reason":"AMBIGUOUS_MATCH","top_score":top_s,"second_score":second}
    return {"resolved":True,"id":str(top["id"]),"score":top_s,"candidate":{k:top.get(k) for k in ("home","away","kickoff")}}
def resolve_espn(match,league_slug):
    try:
        date=(_dt(match.get("kickoff")) or datetime.now(timezone.utc)).strftime("%Y%m%d");payload=_json(f"{ESPNLineupClient.BASE}/{league_slug}/scoreboard?dates={date}");return {"source":"espn",**best_fixture(match,_walk_events(payload)),"league_slug":league_slug}
    except Exception as e:return {"source":"espn","resolved":False,"reason":f"{type(e).__name__}: {e}"}
def resolve_flashscore(match):
    fs=FlashscoreClient();date=(_dt(match.get("kickoff")) or datetime.now(timezone.utc)).strftime("%Y-%m-%d");r=fs.matches(date=date)
    if not r.ok:return {"source":"flashscore","resolved":False,"reason":r.error or "MATCH_LIST_FAILED"}
    return {"source":"flashscore",**best_fixture(match,_walk_events(r.data))}
def _country_hint(competition):
    s=str(competition or "").lower()
    if "turk" in s or "super lig" in s:return "Turkey"
    if "english" in s or "premier league" in s:return "England"
    return None
def resolve_pinnacle(match,league_id):
    r=PinnaclePrematchClient().odds(int(league_id),None)
    if not r.ok:return {"source":"pinnacle","resolved":False,"reason":r.error or "ODDS_FETCH_FAILED"}
    candidates=[];seen=set()
    for row in r.data:
        eid=row.get("event_id")
        if eid in seen:continue
        seen.add(eid);candidates.append({"id":eid,"home":row.get("home"),"away":row.get("away"),"kickoff":row.get("start_time")})
    return {"source":"pinnacle",**best_fixture(match,candidates),"league_id":league_id}
def resolve_provider_ids(*,match:dict[str,Any],espn_league_slug:str|None=None,pinnacle_league_id:int|None=None,**_ignored):
    attempts=[];ids={}
    if espn_league_slug:
        x=resolve_espn(match,espn_league_slug);attempts.append(x);ids["espn_league_slug"]=espn_league_slug
        if x.get("resolved"):ids["espn_event_id"]=x["id"]
    else:attempts.append({"source":"espn","resolved":False,"reason":"ESPN_LEAGUE_SLUG_MISSING"})
    x=resolve_flashscore(match);attempts.append(x)
    if x.get("resolved"):ids["flashscore_match_id"]=x["id"]
    effective_league_id=pinnacle_league_id
    if effective_league_id is None:
        try:
            effective_league_id=PinnaclePrematchClient().discover_league_id(match.get("competition",""),_country_hint(match.get("competition")))
        except Exception:effective_league_id=None
    if effective_league_id is not None:
        ids["pinnacle_league_id"]=int(effective_league_id)
        x=resolve_pinnacle(match,effective_league_id);attempts.append(x)
        if x.get("resolved"):ids["pinnacle_matchup_id"]=x["id"]
    else:attempts.append({"source":"pinnacle","resolved":False,"reason":"PINNACLE_LEAGUE_ID_UNRESOLVED"})
    return {"resolver_version":RESOLVER_VERSION,"resolved_ids":ids,"attempts":attempts,"resolved_sources":sorted([x["source"] for x in attempts if x.get("resolved")]),"unresolved":[{"source":x["source"],"reason":x.get("reason","UNKNOWN")} for x in attempts if not x.get("resolved")]}
