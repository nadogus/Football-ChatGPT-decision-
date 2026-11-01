"""Public deterministic data sources used by Football ChatGPT Decision."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import gzip, json, re, urllib.parse, urllib.request
from data_adapters import FlashscoreClient

UA={"User-Agent":"football-chatgpt-decision/1.0"}

def _text(url:str,timeout=15.0,headers:dict[str,str]|None=None)->str:
    h=dict(UA);h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        if str(r.headers.get("Content-Encoding") or "").lower()=="gzip":
            raw=gzip.decompress(raw)
        return raw.decode("utf-8",errors="replace")

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

class FlashscoreModelClient:
    def __init__(self,base_url=None):self.client=FlashscoreClient(base_url)
    @staticmethod
    def _norm(x):return re.sub(r"[^a-z0-9]+","",str(x or "").lower())
    def team_id(self,team):
        r=self.client.search(team,entity_type="team",sport="football",limit=10)
        if not r.ok:return None
        target=self._norm(team)
        rows=(r.data.get("results") or []) if isinstance(r.data,dict) else []
        exact=[x for x in rows if self._norm(x.get("name"))==target and str(x.get("gender") or "Men").lower()=="men"]
        return str(exact[0]["id"]) if exact else None
    @staticmethod
    def _competition_blocks(payload):
        return payload.get("competitions",[]) if isinstance(payload,dict) else []
    @staticmethod
    def _match_xg(stats):
        if not isinstance(stats,dict):return None
        for period in stats.get("periods",[]) or []:
            if str(period.get("period") or "").lower()!="match":continue
            for group in period.get("groups",[]) or []:
                for row in group.get("statistics",[]) or []:
                    if str(row.get("name") or "").strip().lower() in {"expected goals (xg)","expected goals","xg"}:
                        try:return float(row.get("home_value")),float(row.get("away_value"))
                        except Exception:return None
        return None
    def team_xg_summary(self,team,competition,as_of,last_n=8):
        tid=self.team_id(team)
        if not tid:return None
        r=self.client.team_results(tid,page=1)
        if not r.ok:return None
        candidates=[]
        for block in self._competition_blocks(r.data):
            comp=block.get("competition") or {}
            if self._norm(comp.get("name"))!=self._norm(competition):continue
            for m in block.get("matches",[]) or []:
                try:
                    when=datetime.fromisoformat(str(m.get("start_time")).replace("Z","+00:00"))
                    if when>=as_of:continue
                    if not m.get("has_statistics"):continue
                    candidates.append((when,m))
                except Exception:continue
        candidates.sort(key=lambda z:z[0],reverse=True)
        rows=[]
        for _,m in candidates[:max(last_n*2,last_n)]:
            stat=self.client.statistics(str(m.get("id")),"Match")
            if not stat.ok:continue
            pair=self._match_xg(stat.data)
            if not pair:continue
            hx,ax=pair
            home_id=str((m.get("home") or {}).get("id") or "")
            if home_id==tid:rows.append((hx,ax,m.get("id")))
            else:rows.append((ax,hx,m.get("id")))
            if len(rows)>=last_n:break
        if not rows:return None
        return {"xg_for":sum(x[0] for x in rows)/len(rows),"xg_against":sum(x[1] for x in rows)/len(rows),"matches":len(rows),"match_ids":[x[2] for x in rows],"source":"flashscore_match_statistics"}
    def competition_ref(self,team,competition,as_of):
        tid=self.team_id(team)
        if not tid:return None
        r=self.client.team_results(tid,page=1)
        if not r.ok:return None
        candidates=[]
        for b in self._competition_blocks(r.data):
            comp=b.get("competition") or {}
            if self._norm(comp.get("name"))!=self._norm(competition):continue
            link=comp.get("link");ref_id=comp.get("id");stage=comp.get("stage_id")
            if not link and (not ref_id or not stage):continue
            latest=None
            for m in b.get("matches",[]) or []:
                try:
                    when=datetime.fromisoformat(str(m.get("start_time")).replace("Z","+00:00"))
                    if when<as_of and (latest is None or when>latest):latest=when
                except Exception:pass
            if latest:candidates.append((latest,link or f"{ref_id}:{stage}"))
        candidates.sort(key=lambda z:z[0],reverse=True)
        return candidates[0][1] if candidates else None
    def computed_elo(self,team_seed,competition,as_of,base_rating=1500.0,k=24.0,home_advantage=65.0,max_pages=3):
        ref=self.competition_ref(team_seed,competition,as_of)
        if not ref:return {}
        matches=[];seen=set()
        for page in range(1,max_pages+1):
            r=self.client.tournament_results(ref,page=page)
            if not r.ok:break
            rows=r.data.get("matches",[]) if isinstance(r.data,dict) else []
            if not rows:break
            for m in rows:
                mid=str(m.get("id") or "")
                if mid and mid not in seen:seen.add(mid);matches.append(m)
            pag=r.data.get("pagination") or {}
            if not pag.get("next") and page>=int(pag.get("total_pages") or page):break
        finished=[]
        for m in matches:
            try:
                when=datetime.fromisoformat(str(m.get("start_time")).replace("Z","+00:00"))
                if when>=as_of or str(m.get("status") or "").lower()!="finished":continue
                home=(m.get("home") or {}).get("name");away=(m.get("away") or {}).get("name")
                hs=m.get("home_score");av=m.get("away_score")
                if home and away and hs is not None and av is not None:finished.append((when,home,away,float(hs),float(av)))
            except Exception:continue
        finished.sort(key=lambda x:x[0]);ratings={}
        for _,home,away,hs,av in finished:
            rh=ratings.get(home,base_rating);ra=ratings.get(away,base_rating)
            expected=1/(1+10**(-((rh+home_advantage)-ra)/400))
            actual=1.0 if hs>av else 0.0 if hs<av else 0.5
            margin=max(1.0,abs(hs-av));mult=min(1.75,1.0+0.15*(margin-1.0))
            delta=k*mult*(actual-expected)
            ratings[home]=rh+delta;ratings[away]=ra-delta
        return {name:round(value,3) for name,value in ratings.items()}

class ESPNLeagueModelClient:
    BASE="https://site.api.espn.com/apis/site/v2/sports/soccer"
    def completed_results(self,league_slug,season_start,as_of):
        start=season_start.strftime("%Y%m%d");end=as_of.strftime("%Y%m%d")
        data=_json(f"{self.BASE}/{urllib.parse.quote(league_slug)}/scoreboard?dates={start}-{end}&limit=1000")
        out=[]
        for e in data.get("events",[]) if isinstance(data,dict) else []:
            try:
                when=datetime.fromisoformat(str(e.get("date")).replace("Z","+00:00"))
                if when>=as_of:continue
                status=((e.get("status") or {}).get("type") or {})
                if not status.get("completed"):continue
                comp=(e.get("competitions") or [])[0]
                home=away=None;hs=ascore=None
                for x in comp.get("competitors",[]) or []:
                    name=((x.get("team") or {}).get("displayName") or (x.get("team") or {}).get("name"))
                    score=x.get("score")
                    if isinstance(score,dict):score=score.get("value") or score.get("displayValue")
                    if x.get("homeAway")=="home":home=name;hs=float(score)
                    elif x.get("homeAway")=="away":away=name;ascore=float(score)
                if home and away and hs is not None and ascore is not None:out.append((when,home,away,hs,ascore))
            except Exception:continue
        out.sort(key=lambda x:x[0]);return out
    def computed_elo(self,league_slug,season_start,as_of,base_rating=1500.0,k=24.0,home_advantage=65.0):
        ratings={}
        for _,home,away,hs,ascore in self.completed_results(league_slug,season_start,as_of):
            rh=ratings.get(home,base_rating);ra=ratings.get(away,base_rating)
            expected=1/(1+10**(-((rh+home_advantage)-ra)/400))
            actual=1.0 if hs>ascore else 0.0 if hs<ascore else 0.5
            margin=max(1.0,abs(hs-ascore));mult=min(1.75,1.0+0.15*(margin-1.0))
            delta=k*mult*(actual-expected)
            ratings[home]=rh+delta;ratings[away]=ra-delta
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
        "Accept-Encoding":"identity",
    }
    @staticmethod
    def _decode(html,var_name):
        m=re.search(rf"{re.escape(var_name)}\s*=\s*JSON\.parse\('(.+?)'\)",html,re.S)
        if not m:return None
        try:return json.loads(bytes(m.group(1),"utf-8").decode("unicode_escape"))
        except Exception:return None
    def _ajax(self,path):
        return _json(f"{self.BASE}/{path.lstrip('/')}",timeout=30.0,headers=self.AJAX_HEADERS)
    def league_data(self,league,season):
        slug=urllib.parse.quote(str(league))
        data=self._ajax(f"getLeagueData/{slug}/{int(season)}")
        return data if isinstance(data,dict) else {}
    def computed_elo(self,league,season,as_of,base_rating=1500.0,k=24.0,home_advantage=65.0):
        data=self.league_data(league,season)
        rows=data.get("dates",[]) if isinstance(data,dict) else []
        finished=[]
        for r in rows:
            try:
                if r.get("isResult") is False:continue
                raw_date=r.get("datetime") or r.get("date")
                when=datetime.fromisoformat(str(raw_date).replace("Z","+00:00"))
                if when.tzinfo is None:when=when.replace(tzinfo=timezone.utc)
                if when.astimezone(timezone.utc)>as_of.astimezone(timezone.utc):continue
                home=(r.get("h") or {}).get("title") if isinstance(r.get("h"),dict) else r.get("home")
                away=(r.get("a") or {}).get("title") if isinstance(r.get("a"),dict) else r.get("away")
                goals=r.get("goals") if isinstance(r.get("goals"),dict) else {}
                hs=goals.get("h",r.get("h_goals"))
                av=goals.get("a",r.get("a_goals"))
                if home and away and hs is not None and av is not None:
                    finished.append((when,home,away,float(hs),float(av)))
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
            ratings[home]=rh+delta;ratings[away]=ra-delta
        return {name:round(value,3) for name,value in ratings.items()}
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
