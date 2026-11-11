"""External data adapters. Fail-closed; evidence only; no PLAY/WATCH/PASS logic.
Flashscore (odds, fixtures, statistics) and ESPN (lineups)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json, os, urllib.error, urllib.parse, urllib.request

UA={"User-Agent":"Mozilla/5.0 football-chatgpt-decision/1.0"}
def _json(url:str,timeout:float=20.0,headers:dict[str,str]|None=None)->Any:
    h=dict(UA);h.update(headers or {});req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode("utf-8"))
@dataclass
class AdapterResult:
    source:str;ok:bool;data:Any;error:str|None=None;observed_at:str=""
    def __post_init__(self):
        if not self.observed_at:self.observed_at=datetime.now(timezone.utc).isoformat()
class ESPNLineupClient:
    BASE="https://site.api.espn.com/apis/site/v2/sports/soccer"
    def summary(self,league_slug,event_id):
        try:return AdapterResult("espn",True,_json(f"{self.BASE}/{urllib.parse.quote(league_slug)}/summary?event={urllib.parse.quote(str(event_id))}"))
        except Exception as e:return AdapterResult("espn",False,{},f"{type(e).__name__}: {e}")
    @staticmethod
    def lineup_ids(summary):
        ids=[]
        def walk(x):
            if isinstance(x,dict):
                a=x.get("athlete") if isinstance(x.get("athlete"),dict) else None
                if a and (x.get("starter") is True or x.get("isStarter") is True) and a.get("id") is not None:ids.append(str(a["id"]))
                for v in x.values():walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        walk(summary);return list(dict.fromkeys(ids))
class FlashscoreClient:
    def __init__(self,base_url=None):self.base=(base_url or os.getenv("FLASHSCORE_API_BASE") or "").rstrip("/")
    def _get(self,path,params):
        if not self.base:return AdapterResult("flashscore",False,{},"FLASHSCORE_API_BASE_NOT_CONFIGURED")
        try:return AdapterResult("flashscore",True,_json(self.base+path+"?"+urllib.parse.urlencode(params)))
        except Exception as e:return AdapterResult("flashscore",False,{},f"{type(e).__name__}: {e}")
    def matches(self,sport="football",date=None):
        p={"sport":sport};p.update({"date":date} if date else {});return self._get("/matches",p)
    def details(self,match_id):return self._get("/matches/details",{"match":match_id})
    def lineups(self,match_id):return self._get("/matches/lineups",{"match":match_id})
    def missing_players(self,match_id):return self._get("/matches/missing-players",{"match":match_id})
    def odds(self,match_id,geo=None):
        p={"match":match_id}
        if geo:p["geo"]=geo
        return self._get("/matches/odds",p)
    def statistics(self,match_id,period="Match"):return self._get("/matches/statistics",{"match":match_id,"period":period})
    def search(self,query,entity_type="team",sport="football",limit=10):return self._get("/search",{"query":query,"type":entity_type,"sport":sport,"limit":limit})
    def team_results(self,team_id,page=1):return self._get("/teams/results",{"team":team_id,"page":page})
    def tournament_results(self,tournament_ref,page=1):return self._get("/tournaments/results",{"tournament":tournament_ref,"page":page})
def _flashscore_opening_only(payload):
    """OPENING quotes only where the row really carries an opening value (no fallback to current)."""
    if not (isinstance(payload,dict) and isinstance(payload.get("markets"),list)):return []
    stripped={"markets":[]}
    for market in payload["markets"]:
        if not isinstance(market,dict):continue
        sels=[dict(r,value=r.get("opening_value")) for r in market.get("selections",[]) or [] if isinstance(r,dict) and r.get("opening_value") is not None]
        stripped["markets"].append(dict(market,selections=sels))
    rows=normalize_decimal_quotes(stripped,"flashscore")
    for q in rows:q["phase"]="OPENING"
    return rows
def _flashscore_handicap_value(value):
    if isinstance(value,(int,float)):return float(value)
    if isinstance(value,dict):value=value.get("value")
    if value is None:return None
    import re
    s=str(value)
    m=re.search(r"['\"]value['\"]\s*:\s*['\"]?([+-]?\d+(?:\.\d+)?)",s)
    if not m:m=re.search(r"([+-]?\d+(?:\.\d+)?)",s)
    try:return float(m.group(1)) if m else None
    except Exception:return None

def normalize_decimal_quotes(payload,source,prefer_opening=False,include_opening=False):
    """include_opening=True emits CURRENT and OPENING quotes side by side (for movement)."""
    if source=="flashscore" and include_opening and not prefer_opening:
        cur=normalize_decimal_quotes(payload,source)
        opn=[q for q in _flashscore_opening_only(payload)]
        return cur+opn
    if source=="flashscore" and isinstance(payload,dict) and isinstance(payload.get("markets"),list):
        out=[]
        for market in payload.get("markets",[]):
            if not isinstance(market,dict):continue
            scope=str(market.get("bet_scope") or "").upper()
            if scope and scope!="FULL_TIME":continue
            bet_type=str(market.get("bet_type") or "").upper()
            book=market.get("bookmaker")
            bookmaker=str((book or {}).get("name") if isinstance(book,dict) else book or "flashscore")
            for row in market.get("selections",[]) or []:
                if not isinstance(row,dict):continue
                raw_odd=row.get("opening_value") if prefer_opening else row.get("value")
                if raw_odd is None and prefer_opening:raw_odd=row.get("value")
                try:odd=float(raw_odd)
                except Exception:continue
                if odd<=1:continue
                raw_sel=str(row.get("selection") or "").upper()
                market_name=None;selection=None
                if bet_type=="HOME_DRAW_AWAY":
                    market_name="moneyline"
                    selection={"HOME":"HOME","AWAY":"AWAY","DRAW":"DRAW"}.get(raw_sel)
                elif bet_type=="DRAW_NO_BET":
                    market_name="dnb"
                    selection={"HOME":"HOME_DNB","AWAY":"AWAY_DNB"}.get(raw_sel)
                elif bet_type=="OVER_UNDER":
                    line=_flashscore_handicap_value(row.get("handicap"))
                    if line is not None and raw_sel in {"OVER","UNDER"}:
                        market_name="total";selection=f"{raw_sel}_{line:g}"
                if not selection:continue
                out.append({
                    "market":market_name,
                    "selection":selection,
                    "decimal_odds":odd,
                    "bookmaker":bookmaker,
                    "source":"flashscore",
                    "phase":"OPENING" if prefer_opening else "CURRENT",
                })
        seen=set();clean=[]
        for q in out:
            k=(q["market"],q["selection"],q["decimal_odds"],q["bookmaker"],q["phase"])
            if k not in seen:seen.add(k);clean.append(q)
        return clean
    out=[]
    def walk(x,market=None,book=None):
        if isinstance(x,dict):
            m=str(x.get("market") or x.get("market_name") or market or "");b=str(x.get("bookmaker") or x.get("bookmaker_name") or book or source);sel=x.get("selection") or x.get("outcome") or x.get("name");odd=x.get("decimal_odds",x.get("odds",x.get("price")))
            try:
                o=float(odd)
                if sel and o>1:out.append({"market":m,"selection":str(sel),"decimal_odds":o,"bookmaker":b,"source":source})
            except Exception:pass
            for v in x.values():walk(v,m,b)
        elif isinstance(x,list):
            for v in x:walk(v,market,book)
    walk(payload);seen=set();clean=[]
    for q in out:
        k=(q["market"],q["selection"],q["decimal_odds"],q["bookmaker"])
        if k not in seen:seen.add(k);clean.append(q)
    return clean
