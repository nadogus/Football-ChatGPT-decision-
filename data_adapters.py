"""External data adapters for Football ChatGPT Decision.
Fail-closed; evidence only; no PLAY/WATCH/PASS logic.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json, os, subprocess, sys, urllib.parse, urllib.request

UA={"User-Agent":"Mozilla/5.0 football-chatgpt-decision/1.0"}

def _json(url:str,timeout:float=20.0,headers:dict[str,str]|None=None)->Any:
    h=dict(UA);h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode("utf-8"))

@dataclass
class AdapterResult:
    source:str; ok:bool; data:Any; error:str|None=None; observed_at:str=""
    def __post_init__(self):
        if not self.observed_at:self.observed_at=datetime.now(timezone.utc).isoformat()

class TransfermarktV4Client:
    def __init__(self,base_url=None):self.base=(base_url or os.getenv("TRANSFERMARKT_API_BASE") or "https://transfermarkt-api.fly.dev").rstrip("/")
    def _get(self,path):
        try:return AdapterResult("transfermarkt",True,_json(self.base+path))
        except Exception as e:return AdapterResult("transfermarkt",False,[],f"{type(e).__name__}: {e}")
    def availability(self,player_id):
        q=urllib.parse.quote(str(player_id))
        a=self._get(f"/players/{q}/injuries?page_number=1");b=self._get(f"/players/{q}/absences?page_number=1")
        return AdapterResult("transfermarkt",a.ok or b.ok,{"injuries":a.data if a.ok else [],"absences":b.data if b.ok else []},None if a.ok or b.ok else f"{a.error}; {b.error}")

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

class FotMobLineupClient:
    BASE="https://www.fotmob.com/api"
    def match_details(self,match_id):
        try:return AdapterResult("fotmob",True,_json(f"{self.BASE}/matchDetails?matchId={urllib.parse.quote(str(match_id))}"))
        except Exception as e:return AdapterResult("fotmob",False,{},f"{type(e).__name__}: {e}")
    @staticmethod
    def lineup_ids(payload):
        ids=[]
        def walk(x):
            if isinstance(x,dict):
                pid=x.get("id",x.get("playerId"));bench=x.get("bench",x.get("isBench",False))
                if pid is not None and not bench and ("name" in x or "playerName" in x):ids.append(str(pid))
                for v in x.values():walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        walk(payload.get("content",payload) if isinstance(payload,dict) else payload);return list(dict.fromkeys(ids))

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
    def odds(self,match_id):return self._get("/matches/odds",{"match":match_id})

class PinnaclePrematchClient:
    BASE="https://guest.api.arcadia.pinnacle.com/0.1"
    def __init__(self,api_key=None):self.key=api_key or os.getenv("PINNACLE_GUEST_API_KEY") or ""
    def _headers(self):
        if not self.key:raise RuntimeError("PINNACLE_GUEST_API_KEY_NOT_CONFIGURED")
        return {"X-API-Key":self.key,"Referer":"https://www.pinnacle.com/","Accept":"application/json"}
    @staticmethod
    def american_to_decimal(a):
        try:a=float(a);return round(1+a/100,4) if a>0 else round(1+100/abs(a),4)
        except Exception:return None
    @staticmethod
    def _selection(market,designation,points):
        d=str(designation or "").lower();m=str(market).lower()
        if m=="moneyline":return {"home":"HOME","away":"AWAY","draw":"DRAW"}.get(d,d.upper())
        if m=="total":return ("OVER_" if d=="over" else "UNDER_")+str(points)
        if m=="spread":
            side="HOME" if d=="home" else "AWAY";p=float(points or 0);sign="+" if p>0 else "";return f"{side}_{sign}{p:g}"
        return d.upper()
    def odds(self,league_id:int,matchup_id:int|None=None)->AdapterResult:
        try:
            headers=self._headers()
            ms=_json(f"{self.BASE}/leagues/{int(league_id)}/matchups?brandId=0",headers=headers)
            mk=_json(f"{self.BASE}/leagues/{int(league_id)}/markets/straight?primaryOnly=false",headers=headers)
            now=datetime.now(timezone.utc);matchups={}
            for m in ms:
                try:
                    dt=datetime.fromisoformat(str(m.get("startTime","Z")).replace("Z","+00:00"))
                    if dt>now and not m.get("parent") and m.get("type")!="special":matchups[m["id"]]=m
                except Exception:pass
            rows=[]
            for x in mk:
                if x.get("matchupId") not in matchups or x.get("period")!=0:continue
                mt=str(x.get("type","")).lower()
                if mt not in {"moneyline","spread","total"}:continue
                if matchup_id is not None and str(x.get("matchupId"))!=str(matchup_id):continue
                ev=matchups[x["matchupId"]];parts=ev.get("participants",[])
                home=next((p.get("name") for p in parts if p.get("alignment")=="home"),None);away=next((p.get("name") for p in parts if p.get("alignment")=="away"),None)
                for p in x.get("prices",[]):
                    dec=self.american_to_decimal(p.get("price"));pts=p.get("points")
                    if dec and dec>1:rows.append({"event_id":x["matchupId"],"home":home,"away":away,"start_time":ev.get("startTime"),"market":mt,"selection":self._selection(mt,p.get("designation"),pts),"points":pts,"decimal_odds":dec,"bookmaker":"pinnacle","source":"pinnacle"})
            return AdapterResult("pinnacle",bool(rows),rows,None if rows else "NO_PREMATCH_QUOTES")
        except Exception as e:return AdapterResult("pinnacle",False,[],f"{type(e).__name__}: {e}")

class OddsHarvesterClient:
    def upcoming(self,date_yyyymmdd,markets="1x2,btts,over_under",league=None):
        cmd=[sys.executable,"-m","oddsharvester","upcoming","-s","football","-d",date_yyyymmdd,"-m",markets,"--headless","--stream-ndjson"]
        if league:cmd += ["-l",league]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
            if p.returncode:return AdapterResult("oddsharvester",False,[],p.stderr[-1500:] or f"exit={p.returncode}")
            rows=[]
            for line in p.stdout.splitlines():
                try:
                    o=json.loads(line.strip())
                    if isinstance(o,dict):rows.append(o)
                except Exception:pass
            return AdapterResult("oddsharvester",bool(rows),rows,None if rows else "NO_NDJSON_RECORDS")
        except Exception as e:return AdapterResult("oddsharvester",False,[],f"{type(e).__name__}: {e}")

def normalize_decimal_quotes(payload,source):
    if source=="pinnacle" and isinstance(payload,list):return payload
    out=[]
    def walk(x,market=None,book=None):
        if isinstance(x,dict):
            m=str(x.get("market") or x.get("market_name") or market or "");b=str(x.get("bookmaker") or x.get("bookmaker_name") or book or source)
            sel=x.get("selection") or x.get("outcome") or x.get("name");odd=x.get("decimal_odds",x.get("odds",x.get("price")))
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
