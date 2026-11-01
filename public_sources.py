"""Public deterministic data sources used by Football ChatGPT Decision."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import json, re, urllib.parse, urllib.request

UA={"User-Agent":"football-chatgpt-decision/1.0"}

def _text(url:str,timeout=15.0)->str:
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8",errors="replace")

def _json(url:str,timeout=15.0)->Any:
    return json.loads(_text(url,timeout))

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

class ClubEloClient:
    API_BASE="http://api.clubelo.com"; WEB_BASE="https://clubelo.com"
    @staticmethod
    def _parse_csv(text):
        lines=[x for x in text.splitlines() if x.strip()]
        if len(lines)<2:return []
        header=[x.strip() for x in lines[0].split(",")]
        if "Elo" not in header:return []
        return [dict(zip(header,row.split(","))) for row in lines[1:] if row]
    def club_history(self,club):
        slug=urllib.parse.quote(club.replace(" ",""))
        try:
            rows=self._parse_csv(_text(f"{self.API_BASE}/{slug}"))
            if rows:return rows
        except Exception:pass
        return []
    def latest_elo(self,club,as_of=None):
        rows=self.club_history(club)
        if not rows:return None
        d=(as_of or datetime.now(timezone.utc)).date().isoformat()
        valid=[r for r in rows if r.get("From","")<=d and r.get("Elo")]
        try:return float(valid[-1]["Elo"]) if valid else None
        except Exception:return None

class UnderstatClient:
    BASE="https://understat.com"
    @staticmethod
    def _decode(html,var_name):
        m=re.search(rf"{re.escape(var_name)}\s*=\s*JSON\.parse\('(.+?)'\)",html,re.S)
        if not m:return None
        try:return json.loads(bytes(m.group(1),"utf-8").decode("unicode_escape"))
        except Exception:return None
    def team_history(self,team,season):
        slug=urllib.parse.quote(team.replace(" ","_"))
        data=self._decode(_text(f"{self.BASE}/team/{slug}/{season}"),"datesData")
        return data if isinstance(data,list) else []
    def team_xg_summary(self,team,season,last_n=10):
        rows=self.team_history(team,season)[-last_n:]
        xf=xa=0.0;n=0
        for r in rows:
            try:
                xg=r.get("xG",{}); side=r.get("side")
                if side not in {"h","a"} or not isinstance(xg,dict):continue
                xf+=float(xg[side]); xa+=float(xg["a" if side=="h" else "h"]); n+=1
            except Exception:continue
        return {"xg_for":xf/n,"xg_against":xa/n,"matches":n} if n else None
