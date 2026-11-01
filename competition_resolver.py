"""Generic competition resolution and league capability checks.

No league-specific betting logic lives here. The resolver derives competition identity
from Flashscore metadata, matches that identity against Pinnacle's live catalog, and
reports whether xG/Elo/odds evidence paths are available. Fail closed on ambiguity.
"""
from __future__ import annotations
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
import re, unicodedata
from data_adapters import FlashscoreClient, PinnaclePrematchClient
from public_sources import FlashscoreModelClient

RESOLVER_VERSION="COMPETITION_RESOLVER_V1.1"

STOPWORDS={"football","soccer","league","liga","ligue","lig","serie","division","championship","the"}

def norm(value:Any)->str:
    s=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return " ".join(s.split())

def compact(value:Any)->str:
    return re.sub(r"[^a-z0-9]+","",norm(value))

def tokens(value:Any)->set[str]:
    return {x for x in norm(value).split() if x not in STOPWORDS and len(x)>1}

def text_similarity(a:Any,b:Any)->float:
    aa,bb=norm(a),norm(b)
    if not aa or not bb:return 0.0
    if aa==bb:return 1.0
    ta,tb=tokens(aa),tokens(bb)
    jac=len(ta&tb)/len(ta|tb) if ta|tb else 0.0
    seq=SequenceMatcher(None,aa,bb).ratio()
    ca,cb=compact(aa),compact(bb)
    contains=1.0 if ca and cb and (ca in cb or cb in ca) else 0.0
    return max(seq,0.65*jac+0.35*seq,0.92*contains)

def _parse_dt(value:Any)->datetime|None:
    if value is None:return None
    if isinstance(value,(int,float)):
        try:
            ts=float(value)
            if ts>10_000_000_000:ts/=1000.0
            return datetime.fromtimestamp(ts,tz=timezone.utc)
        except Exception:return None
    try:
        x=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc)
    except Exception:return None

def _match_time(match:dict[str,Any])->datetime|None:
    for key in ("start_time","startTime","utcTime","start","date","timestamp","startTimestamp"):
        x=_parse_dt(match.get(key))
        if x:return x
    return None

def _match_competition(match:dict[str,Any])->dict[str,Any]:
    for key in ("competition","tournament","league"):
        value=match.get(key)
        if isinstance(value,dict):return value
    return {}

def _match_list(payload:Any)->list[dict[str,Any]]:
    if isinstance(payload,list):return [x for x in payload if isinstance(x,dict)]
    if not isinstance(payload,dict):return []
    for key in ("matches","events","results"):
        rows=payload.get(key)
        if isinstance(rows,list):return [x for x in rows if isinstance(x,dict)]
    return []

def _competition_blocks(payload:Any)->list[dict[str,Any]]:
    """Normalize the Flashscore scraper's observed team-results response shapes.

    Older fixtures/tests used {competitions:[{competition:{...}, matches:[...]}]}.
    The live scraper can also return a flat match list (or {matches:[...]}) where
    competition/tournament metadata is attached to each match. Keep both paths so
    runtime resolution follows provider data instead of a synthetic-only shape.
    """
    if isinstance(payload,dict) and isinstance(payload.get("competitions"),list):
        return [x for x in payload["competitions"] if isinstance(x,dict)]
    rows=_match_list(payload)
    grouped:dict[tuple[str,str,str,str],dict[str,Any]]={}
    for match in rows:
        comp=_match_competition(match)
        name=comp.get("name") or match.get("competition_name") or match.get("tournament_name")
        display=comp.get("display_name") or comp.get("displayName") or match.get("competition_display_name")
        link=comp.get("link") or comp.get("url") or match.get("competition_link")
        cid=comp.get("id") or comp.get("tournament_id") or match.get("competition_id") or match.get("tournament_id")
        stage=comp.get("stage_id") or comp.get("stageId") or match.get("stage_id")
        category=comp.get("category") or comp.get("country") or match.get("country")
        if not name and not display and not link:continue
        key=(str(cid or ""),str(stage or ""),str(name or display or ""),str(link or ""))
        block=grouped.setdefault(key,{"competition":{
            "id":cid,"stage_id":stage,"name":name or display,"display_name":display or name,
            "category":category,"country":comp.get("country"),"link":link,
        },"matches":[]})
        block["matches"].append(match)
    return list(grouped.values())

class FlashscoreCompetitionResolver:
    def __init__(self,base_url=None):
        self.client=FlashscoreClient(base_url)

    def team_id(self,team:str)->str|None:
        r=self.client.search(team,entity_type="team",sport="football",limit=10)
        if not r.ok or not isinstance(r.data,dict):return None
        target=compact(team)
        rows=r.data.get("results") or []
        candidates=[]
        for row in rows:
            if not isinstance(row,dict) or not row.get("id"):continue
            if str(row.get("gender") or "Men").lower()!="men":continue
            score=text_similarity(team,row.get("name"))
            if compact(row.get("name"))==target:score=1.0
            candidates.append((score,row))
        candidates.sort(key=lambda z:z[0],reverse=True)
        return str(candidates[0][1]["id"]) if candidates and candidates[0][0]>=0.82 else None

    def profile(self,team:str,competition:str,as_of:datetime|None=None)->dict[str,Any]|None:
        tid=self.team_id(team)
        if not tid:return None
        r=self.client.team_results(tid,page=1)
        if not r.ok:return None
        candidates=[]
        for block in _competition_blocks(r.data):
            comp=block.get("competition") or {}
            if not isinstance(comp,dict):continue
            name=comp.get("name") or comp.get("displayName")
            display=comp.get("display_name") or comp.get("displayName") or name
            score=max(text_similarity(competition,name),text_similarity(competition,display))
            if score<0.55:continue
            if as_of is not None:
                if not any((when:=_match_time(m)) is not None and when<as_of for m in block.get("matches",[]) or []):continue
            country_obj=comp.get("country")
            country=(country_obj or {}).get("name") if isinstance(country_obj,dict) else country_obj
            category=comp.get("category")
            if not country and isinstance(category,dict):country=category.get("name")
            country=country or category
            candidates.append((score,{
                "source":"flashscore",
                "team_id":tid,
                "competition_id":comp.get("id"),
                "stage_id":comp.get("stage_id") or comp.get("stageId"),
                "name":name,
                "display_name":display,
                "country":country,
                "link":comp.get("link") or comp.get("url"),
                "score":round(score,6),
            }))
        candidates.sort(key=lambda z:z[0],reverse=True)
        if not candidates:return None
        top_score,top=candidates[0]
        second=candidates[1][0] if len(candidates)>1 else 0.0
        if top_score<0.72 or (len(candidates)>1 and top_score-second<0.05):return None
        return top

def pinnacle_catalog_match(profile:dict[str,Any],rows:list[dict[str,Any]],threshold:float=.68,margin:float=.06)->dict[str,Any]:
    comp=profile.get("name") or profile.get("display_name")
    display=profile.get("display_name") or comp
    country=profile.get("country")
    scored=[]
    for row in rows or []:
        if not isinstance(row,dict) or row.get("id") is None:continue
        name=row.get("name");group=row.get("group")
        name_score=max(text_similarity(comp,name),text_similarity(display,name))
        country_score=text_similarity(country,group) if country and group else 0.0
        total=.72*name_score+.28*country_score
        if norm(country) and norm(group)==norm(country):total+=.12
        if tokens(comp) and tokens(comp)<=tokens(name):total+=.08
        requested_terms=tokens(str(comp)+" "+str(display))
        catalog_terms=tokens(name)
        variant_terms={"women","woman","womens","u17","u18","u19","u20","u21","u23","reserve","reserves","youth"}
        extra_variants=(catalog_terms & variant_terms)-(requested_terms & variant_terms)
        if extra_variants:total-=.22
        scored.append((max(0.0,min(total,1.0)),row))
    scored.sort(key=lambda z:z[0],reverse=True)
    if not scored:return {"resolved":False,"reason":"NO_CATALOG_CANDIDATES"}
    top_s,top=scored[0];second=scored[1][0] if len(scored)>1 else 0.0
    if top_s<threshold:return {"resolved":False,"reason":"LOW_LEAGUE_SCORE","top_score":round(top_s,6)}
    if len(scored)>1 and top_s-second<margin:return {"resolved":False,"reason":"AMBIGUOUS_LEAGUE","top_score":round(top_s,6),"second_score":round(second,6)}
    return {"resolved":True,"league_id":int(top["id"]),"score":round(top_s,6),"catalog_name":top.get("name"),"catalog_group":top.get("group")}

def resolve_pinnacle_league(profile:dict[str,Any],client:PinnaclePrematchClient|None=None)->dict[str,Any]:
    client=client or PinnaclePrematchClient();r=client.leagues(29)
    if not r.ok:return {"resolved":False,"reason":r.error or "PINNACLE_CATALOG_UNAVAILABLE"}
    return pinnacle_catalog_match(profile,r.data)

def league_capability(*,home:str,away:str,competition:str,kickoff:str|datetime,flashscore_base_url:str|None=None,check_pinnacle:bool=True)->dict[str,Any]:
    as_of=kickoff if isinstance(kickoff,datetime) else datetime.fromisoformat(str(kickoff).replace("Z","+00:00"))
    if as_of.tzinfo is None:as_of=as_of.replace(tzinfo=timezone.utc)
    resolver=FlashscoreCompetitionResolver(flashscore_base_url);profile=resolver.profile(home,competition,as_of=as_of)
    result={"resolver_version":RESOLVER_VERSION,"competition_requested":competition,"profile":profile,"checks":{"competition_profile":bool(profile),"xg":False,"elo":False,"pinnacle_league":False},"details":{},"status":"UNSUPPORTED"}
    if not profile:
        result["details"]["competition_profile"]="FLASH_SCORE_COMPETITION_UNRESOLVED";return result
    model=FlashscoreModelClient(flashscore_base_url);fs_comp=profile.get("name") or competition
    hx=model.team_xg_summary(home,fs_comp,as_of,last_n=8);ax=model.team_xg_summary(away,fs_comp,as_of,last_n=8)
    result["details"]["xg"]={"home":hx,"away":ax};result["checks"]["xg"]=bool(hx and ax)
    ratings=model.computed_elo(home,fs_comp,as_of);home_key=compact(home);away_key=compact(away)
    he=next((v for k,v in ratings.items() if compact(k)==home_key),None);ae=next((v for k,v in ratings.items() if compact(k)==away_key),None)
    result["details"]["elo"]={"home":he,"away":ae};result["checks"]["elo"]=he is not None and ae is not None
    if check_pinnacle:
        p=resolve_pinnacle_league(profile);result["details"]["pinnacle_league"]=p;result["checks"]["pinnacle_league"]=bool(p.get("resolved"))
    else:result["details"]["pinnacle_league"]={"resolved":None,"reason":"NOT_CHECKED"}
    core=result["checks"]
    if core["competition_profile"] and core["xg"] and core["elo"] and (core["pinnacle_league"] or not check_pinnacle):result["status"]="SUPPORTED"
    elif core["competition_profile"]:result["status"]="PARTIAL"
    return result
