"""Diagnostics for public model-input sources. No secrets, no decisions."""
from __future__ import annotations
import json,re,urllib.request
from datetime import datetime,timezone
from public_sources import _text, UnderstatClient, SofaScoreClient

def probe(url,headers=None):
    out={"url":url}
    try:
        req=urllib.request.Request(url,headers=headers or {"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=15) as r:
            raw=r.read()
            body=raw.decode("utf-8",errors="replace")
            out.update({
                "ok":True,"status":getattr(r,"status",None),"length":len(body),
                "content_type":r.headers.get("Content-Type"),
                "content_encoding":r.headers.get("Content-Encoding"),
                "prefix":body[:180],
            })
    except Exception as e:
        out.update({"ok":False,"error":f"{type(e).__name__}: {e}"})
    return out

def call(name,fn):
    try:
        value=fn()
        if isinstance(value,dict):
            summary={"type":"dict","keys":list(value.keys())[:20]}
            if "dates" in value:summary["dates_count"]=len(value.get("dates") or [])
            if "seasons" in value:summary["seasons_count"]=len(value.get("seasons") or [])
            return {"ok":True,"summary":summary}
        if isinstance(value,list):return {"ok":True,"summary":{"type":"list","count":len(value),"first":value[:1]}}
        return {"ok":True,"summary":{"type":type(value).__name__,"value":value}}
    except Exception as e:
        return {"ok":False,"error":f"{type(e).__name__}: {e}"}

u=UnderstatClient()
s=SofaScoreClient()
report={
    "understat_page":probe("https://understat.com/team/Liverpool/2026"),
    "understat_ajax_raw":probe("https://understat.com/getTeamData/Liverpool/2026",u.AJAX_HEADERS),
    "understat_ajax_client":call("understat",lambda:u._ajax("getTeamData/Liverpool/2026")),
    "sofa_seasons_raw":probe("https://api.sofascore.com/api/v1/unique-tournament/17/seasons"),
    "sofa_seasons_client":call("seasons",lambda:s.tournament_seasons(17)),
    "sofa_events_raw":probe("https://api.sofascore.com/api/v1/unique-tournament/17/season/96668/events/last/0"),
    "sofa_events_client":call("events",lambda:s.season_events(17,96668,max_pages=1)),
    "sofa_elo_client":call("elo",lambda:s.computed_elo(17,datetime(2026,11,1,16,30,tzinfo=timezone.utc))),
    "clubelo_api_https":probe("https://api.clubelo.com/Liverpool"),
    "clubelo_api_http":probe("http://api.clubelo.com/Liverpool"),
    "clubelo_web":probe("https://clubelo.com/Liverpool"),
}
print(json.dumps(report,indent=2))
with open("MODEL_SOURCE_DIAGNOSTICS.json","w") as f:json.dump(report,f,indent=2)
