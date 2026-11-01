"""Public deterministic data sources used by Football ChatGPT Decision."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import json, re, urllib.parse, urllib.request

UA={"User-Agent":"football-chatgpt-decision/1.0"}

def _text(url:str,timeout=15.0,headers:dict[str,str]|None=None)->str:
    h=dict(UA);h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8",errors="replace")

def _json(url:str,timeout=15.0,headers:dict[str,str]|None=None)->Any:
    return json.loads(_text(url,timeout,headers))

class SofaScoreClient:
    BASE="https://www.sofascore.com/api/v1"
    def event(self,event_id):return _json(f"{self.BASE}/event/{event_id}").get("event",{})
    def lineups(self,event_id):return _json(f"{self.BASE}/event/{event_id}/lineups")
    def snapshot(self,event_id):
        e=self.event(event_id)
        if not e: raise ValueError(f"SofaScore event not found: {event_id}")
        ts=e.get("startTimestamp")
        return {
            "match_id":str(e.get("id",event_id)),
            "kickoff":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat() if ts else None,
            "home":e.get("homeTeam",{}).get("name","Unknown"),
            "away":e.get("awayTeam",{}).get("name","Unknown"),
            "competition":e.get("tournament",{}).get("name","Unknown"),
            "raw":e,
        }
    def tournament_seasons(self,unique_tournament_id:int)->list[dict[str,Any]]:
        data=_json(f"{self.BASE}/unique-tournament/{int(unique_tournament_id)}/seasons")
        return data.get("seasons",[]) if isinstance(data,dict) else []
    def season_id_for_date(self,unique_tournament_id:int,as_of:datetime)->int|None:
        y=as_of.year%100
        start=y if as_of.month>=7 else (y-1)%100
        key=f"{start:02d}/{(start+1)%100:02d}"
        for s in self.tournament_seasons(unique_tournament_id):
            if str(s.get("year") or "")==key:
                try:return int(s["id"])
                except Exception:return None
        return None
    def season_events(self,unique_tournament_id:int,season_id:int,max_pages:int=20)->list[dict[str,Any]]:
        events=[]
        for page in range(max_pages):
            try:data=_json(f"{self.BASE}/unique-tournament/{int(unique_tournament_id)}/season/{int(season_id)}/events/last/{page}")
            except Exception:
                if page==0:raise
                break
            rows=data.get("events",[]) if isinstance(data,dict) else []
            if not rows:break
            events.extend(x for x in rows if isinstance(x,dict))
            if not data.get("hasNextPage"):break
        return events
    def computed_elo(self,unique_tournament_id:int,as_of:datetime,base_rating:float=1500.0,k:float=24.0,home_advantage:float=65.0)->dict[str,float]:
        season_id=self.season_id_for_date(unique_tournament_id,as_of)
        if season_id is None:return {}
        events=self.season_events(unique_tournament_id,season_id)
        finished=[]
        for e in events:
            try:
                ts=int(e.get("startTimestamp") or 0)
                when=datetime.fromtimestamp(ts,tz=timezone.utc)
                status=str((e.get("status") or {}).get("type") or "").lower()
                if when>as_of or status!="finished":continue
                h=(e.get("homeTeam") or {}).get("name")
                a=(e.get("awayTeam") or {}).get("name")
                hs=(e.get("homeScore") or {}).get("current")
                av=(e.get("awayScore") or {}).get("current")
                if h and a and hs is not None and av is not None:
                    finished.append((when,h,a,float(hs),float(av)))
            except Exception:continue
        finished.sort(key=lambda x:x[0])
        ratings={}
        for _,home,away,hs,av in finished:
            rh=ratings.get(home,base_rating);ra=ratings.get(away,base_rating)
            expected=1/(1+10**(-((rh+home_advantage)-ra)/400))
            actual=1.0 if hs>av else 0.0 if hs<av else 0.5
            margin=max(1.0,abs(hs-av))
            mult=min(1.75,1.0+0.15*(margin-1.0))
            delta=k*mult*(actual-expected)
            ratings[home]=rh+delta
            ratings[away]=ra-delta
        return {name:round(value,3) for name,value in ratings.items()}

class ClubEloClient:
    API_BASE="http://api.clubelo.com"; WEB_BASE="https://clubelo.com"
    @staticmethod
    def _parse_csv(text):
        lines=[x for x in text.splitlines() if x.strip()]
        if len(lines)<2:return []
        header=[x.strip() for x in lines[0].split(",")]
        if "Elo" not in header:return []
        return [dict(zip(header,row.split(","))) for row in lines[1:] if row]
    @staticmethod
    def _parse_web_history(html):
        candidates=[]
        m=re.search(r"vegaJson\s*=\s*(\{.*?\})\s*;",html,re.S)
        if m:
            try:candidates.append(json.loads(m.group(1)))
            except Exception:pass
        m=re.search(r"vegaJson\s*=\s*JSON\.parse\('(.+?)'\)",html,re.S)
        if m:
            try:candidates.append(json.loads(bytes(m.group(1),"utf-8").decode("unicode_escape")))
            except Exception:pass
        rows=[]
        def walk(x):
            if isinstance(x,dict):
                if "Elo" in x and ("Date" in x or "From" in x):
                    rows.append({"From":str(x.get("From") or x.get("Date") or "")[:10],"Elo":str(x.get("Elo") or "")})
                for v in x.values():walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        for x in candidates:walk(x)
        rows=[r for r in rows if r.get("From") and r.get("Elo")]
        rows.sort(key=lambda r:r["From"])
        return rows
    def club_history(self,club):
        slug=urllib.parse.quote(club.replace(" ",""))
        try:
            rows=self._parse_csv(_text(f"{self.API_BASE}/{slug}"))
            if rows:return rows
        except Exception:pass
        try:return self._parse_web_history(_text(f"{self.WEB_BASE}/{slug}"))
        except Exception:return []
    def latest_elo(self,club,as_of=None):
        rows=self.club_history(club)
        if not rows:return None
        d=(as_of or datetime.now(timezone.utc)).date().isoformat()
        valid=[r for r in rows if r.get("From","")<=d and r.get("Elo")]
        try:return float(valid[-1]["Elo"]) if valid else None
        except Exception:return None

class UnderstatClient:
    BASE="https://understat.com"
    AJAX_HEADERS={
        "User-Agent":"Mozilla/5.0",
        "X-Requested-With":"XMLHttpRequest",
        "Referer":"https://understat.com/",
        "Accept":"application/json, text/javascript, */*; q=0.01",
    }
    @staticmethod
    def _decode(html,var_name):
        m=re.search(rf"{re.escape(var_name)}\s*=\s*JSON\.parse\('(.+?)'\)",html,re.S)
        if not m:return None
        try:return json.loads(bytes(m.group(1),"utf-8").decode("unicode_escape"))
        except Exception:return None
    def _ajax(self,path):
        return _json(f"{self.BASE}/{path.lstrip('/')}",timeout=30.0,headers=self.AJAX_HEADERS)
    def team_history(self,team,season):
        slug=urllib.parse.quote(team.replace(" ","_"))
        try:
            data=self._ajax(f"getTeamData/{slug}/{int(season)}")
            rows=data.get("dates",[]) if isinstance(data,dict) else []
            if isinstance(rows,list):return rows
        except Exception:pass
        try:
            data=self._decode(_text(f"{self.BASE}/team/{slug}/{season}"),"datesData")
            if isinstance(data,dict):data=data.get("dates",[])
            return data if isinstance(data,list) else []
        except Exception:return []
    @staticmethod
    def _same_team(a,b):
        norm=lambda x:re.sub(r"[^a-z0-9]+","",str(x or "").lower())
        return bool(norm(a)) and norm(a)==norm(b)
    def team_xg_summary(self,team,season,last_n=10):
        rows=self.team_history(team,season)
        parsed=[]
        for r in rows:
            try:
                if r.get("isResult") is False:continue
                if not isinstance(r.get("xG"),dict) and r.get("xG") is not None and r.get("xGA") is not None:
                    parsed.append((float(r["xG"]),float(r["xGA"])))
                    continue
                xg=r.get("xG",{})
                if not isinstance(xg,dict):continue
                side=r.get("side") or r.get("h_a")
                if side in {"h","a"}:
                    parsed.append((float(xg[side]),float(xg["a" if side=="h" else "h"])))
                    continue
                home=(r.get("h") or {}).get("title") if isinstance(r.get("h"),dict) else None
                away=(r.get("a") or {}).get("title") if isinstance(r.get("a"),dict) else None
                if self._same_team(team,home):
                    parsed.append((float(xg["h"]),float(xg["a"])))
                elif self._same_team(team,away):
                    parsed.append((float(xg["a"]),float(xg["h"])))
            except Exception:continue
        parsed=parsed[-last_n:]
        if not parsed:return None
        return {
            "xg_for":sum(x[0] for x in parsed)/len(parsed),
            "xg_against":sum(x[1] for x in parsed)/len(parsed),
            "matches":len(parsed),
            "season":int(season),
            "source":"understat_ajax",
        }
