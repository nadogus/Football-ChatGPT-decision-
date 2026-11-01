"""Football ChatGPT Decision — deterministic evidence engine V1.

This module calculates evidence. It NEVER assigns PLAY/WATCH/PASS.
Final betting authority belongs to ChatGPT under CHATGPT_DECISION_POLICY.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
import json, math, statistics, hashlib
from pathlib import Path

@dataclass
class SourceDatum:
    source: str
    observed_at: datetime
    reliability: float
    max_age_seconds: int
    payload: dict[str, Any] = field(default_factory=dict)
    def age_seconds(self, now=None):
        now = now or datetime.now(timezone.utc)
        t = self.observed_at if self.observed_at.tzinfo else self.observed_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now-t).total_seconds())
    def fresh(self, now=None): return self.age_seconds(now) <= self.max_age_seconds

@dataclass
class MarketQuote:
    market: str
    selection: str
    decimal_odds: float
    bookmaker: str
    observed_at: datetime
    phase: str = "CURRENT"
    def __post_init__(self):
        if self.decimal_odds <= 1: raise ValueError("decimal_odds must be > 1")

SOURCE_POLICY = {
 "sofascore:event":(.82,21600), "sofascore:lineups":(.88,1800),
 "understat":(.86,86400), "clubelo":(.90,86400), "transfermarkt":(.78,21600),
 "fotmob":(.80,7200), "espn":(.80,7200), "oddsharvester":(.78,1200),
 "flashscore:odds":(.80,900), "pinnacle":(.92,600), "draftkings":(.85,600)
}

def integrity(sources:list[SourceDatum], league_coverage:float=1.0, now=None):
    flags=[]
    if not sources: return {"data_quality":0.0,"league_coverage":league_coverage,"flags":["NO_SOURCE_DATA","LOW_DATA_QUALITY"]}
    num=den=0.0
    for d in sources:
        w=max(.01,d.reliability); score=d.reliability
        if not d.fresh(now): score*=.25; flags.append(f"STALE:{d.source}")
        num+=score*w; den+=w
    q=(num/den)*max(.25,min(1.0,league_coverage))
    if league_coverage<.70: flags.append("LOW_LEAGUE_COVERAGE")
    if q<.55: flags.append("LOW_DATA_QUALITY")
    return {"data_quality":round(q,4),"league_coverage":league_coverage,"flags":sorted(set(flags))}

def poisson_pmf(k:int, lam:float): return math.exp(-lam)*(lam**k)/math.factorial(k)

def dc_tau(h,a,hx,ax,rho=-.08):
    if h==0 and a==0:return 1-(hx*ax*rho)
    if h==0 and a==1:return 1+(hx*rho)
    if h==1 and a==0:return 1+(ax*rho)
    if h==1 and a==1:return 1-rho
    return 1.0

def score_matrix(home_xg:float, away_xg:float, max_goals:int=8, rho:float=-.08):
    m={}; total=0.0
    for h in range(max_goals+1):
        for a in range(max_goals+1):
            p=poisson_pmf(h,home_xg)*poisson_pmf(a,away_xg)*dc_tau(h,a,home_xg,away_xg,rho)
            m[(h,a)]=max(0,p); total+=m[(h,a)]
    return {k:v/total for k,v in m.items()}

def scoreline_markets(home_xg:float, away_xg:float):
    m=score_matrix(home_xg,away_xg)
    home=sum(p for (h,a),p in m.items() if h>a); draw=sum(p for (h,a),p in m.items() if h==a); away=1-home-draw
    btts=sum(p for (h,a),p in m.items() if h>0 and a>0); over25=sum(p for (h,a),p in m.items() if h+a>=3)
    return {"HOME":home,"DRAW":draw,"AWAY":away,"BTTS_YES":btts,"OVER_2.5":over25,"UNDER_2.5":1-over25,
            "HOME_DNB":home/(home+away) if home+away else .5,"AWAY_DNB":away/(home+away) if home+away else .5,
            "1X":home+draw,"X2":away+draw}

def elo_1x2(home_elo:float, away_elo:float, home_advantage:float=65.0, draw_base:float=.25):
    diff=(home_elo+home_advantage)-away_elo
    non_draw_home=1/(1+10**(-diff/400)); draw=max(.12,min(.32,draw_base*math.exp(-abs(diff)/900)))
    return {"HOME":(1-draw)*non_draw_home,"DRAW":draw,"AWAY":(1-draw)*(1-non_draw_home)}

def ensemble(models:list[dict[str,float]], weights:list[float]|None=None):
    if not models:return {},0.0
    weights=weights or [1.0]*len(models); keys=set().union(*(m.keys() for m in models)); out={}
    for k in keys:
        pairs=[(m[k],w) for m,w in zip(models,weights) if k in m]
        out[k]=sum(v*w for v,w in pairs)/sum(w for _,w in pairs)
    vals=[]
    for k in ("HOME","DRAW","AWAY"):
        xs=[m[k] for m in models if k in m]
        if len(xs)>1: vals.append(statistics.pstdev(xs))
    dispersion=sum(vals)/len(vals) if vals else 0.0
    return out, max(0.0,min(1.0,1-dispersion/.18))

def proportional_devig(decimal_odds:dict[str,float]):
    raw={k:1/v for k,v in decimal_odds.items()}; z=sum(raw.values())
    return {k:v/z for k,v in raw.items()}

def fair_odds(p:float): return None if p<=0 else 1/p

def edge_ev(p:float, odds:float): return {"edge_pp":p-(1/odds),"ev":p*odds-1}

def best_prices(quotes:list[MarketQuote]):
    best={}
    for q in quotes:
        key=(q.market,q.selection)
        if key not in best or q.decimal_odds>best[key].decimal_odds: best[key]=q
    return best

def market_consensus(quotes:list[MarketQuote], market:str):
    books={}
    for q in quotes:
        if q.market==market: books.setdefault(q.bookmaker,{})[q.selection]=q.decimal_odds
    probs=[]
    for odds in books.values():
        if len(odds)>=2: probs.append(proportional_devig(odds))
    keys=set().union(*(p.keys() for p in probs)) if probs else set()
    return {k:sum(p.get(k,0) for p in probs)/len(probs) for k in keys} if probs else {}

def movement(opening:float,current:float): return current/opening-1

CORRELATION_FAMILY={
 "HOME":"HOME_SIDE","HOME_ML":"HOME_SIDE","HOME_DNB":"HOME_SIDE","HOME_-0.25":"HOME_SIDE","HOME_-0.5":"HOME_SIDE",
 "AWAY":"AWAY_SIDE","AWAY_ML":"AWAY_SIDE","AWAY_DNB":"AWAY_SIDE","AWAY_+0.25":"AWAY_SIDE","AWAY_+0.5":"AWAY_SIDE",
 "UNDER_2.5":"TOTAL_UNDER","UNDER_3.0":"TOTAL_UNDER","UNDER_3.5":"TOTAL_UNDER",
 "OVER_2.5":"TOTAL_OVER","OVER_3.0":"TOTAL_OVER","OVER_3.5":"TOTAL_OVER"}

def candidate_evidence(probabilities:dict[str,float], quotes:list[MarketQuote]):
    """Return ALL candidates. Correlation is metadata, never a destructive filter."""
    rows=[]
    for (market,selection),q in best_prices(quotes).items():
        if selection not in probabilities: continue
        p=probabilities[selection]; ee=edge_ev(p,q.decimal_odds)
        rows.append({"market":market,"selection":selection,"model_probability":round(p,6),"fair_odds":round(fair_odds(p),4),
                     "best_odds":q.decimal_odds,"bookmaker":q.bookmaker,"edge_pp":round(ee["edge_pp"],6),"ev":round(ee["ev"],6),
                     "correlation_family":CORRELATION_FAMILY.get(selection,selection)})
    return sorted(rows,key=lambda x:x["ev"],reverse=True)

def build_evidence_packet(*,match:dict[str,Any],sources:list[SourceDatum],league_coverage:float,models:dict[str,dict[str,float]],quotes:list[MarketQuote],
                          xi:dict[str,Any]|None=None,context:dict[str,Any]|None=None,engine_version="evidence-v1.0"):
    integ=integrity(sources,league_coverage); names=list(models); model_list=[models[n] for n in names]
    combined,agreement=ensemble(model_list)
    packet={"schema_version":"1.0","engine_version":engine_version,"generated_at":datetime.now(timezone.utc).isoformat(),
            "match":match,"stage":"POST_XI" if (xi or {}).get("official_verified") else "PRE",
            "integrity":integ,"source_evidence":[{"source":s.source,"observed_at":s.observed_at.isoformat(),"reliability":s.reliability,"fresh":s.fresh()} for s in sources],
            "models":{"individual":models,"ensemble":combined,"model_agreement":round(agreement,4)},
            "market":{"consensus_1x2":market_consensus(quotes,"1X2"),"candidates":candidate_evidence(combined,quotes)},
            "xi":xi or {"official_verified":False},"context":context or {},
            "decision_authority":"CHATGPT_ONLY","production_decision":None,
            "warnings":integ["flags"]}
    return packet

class ImmutableLedger:
    def __init__(self,path="ledger/evidence.jsonl"): self.path=Path(path)
    def append(self,packet):
        self.path.parent.mkdir(parents=True,exist_ok=True); raw=json.dumps(packet,sort_keys=True,separators=(",",":"),default=str)
        record={"sha256":hashlib.sha256(raw.encode()).hexdigest(),"packet":packet}
        with self.path.open("a",encoding="utf-8") as f:f.write(json.dumps(record,ensure_ascii=False,default=str)+"\n")
        return record["sha256"]

if __name__=="__main__":
    # deterministic smoke test: calculations only, no betting decision
    dc=scoreline_markets(1.65,1.05); elo=elo_1x2(1700,1620); ens,agr=ensemble([dc,elo])
    assert abs(dc["HOME"]+dc["DRAW"]+dc["AWAY"]-1)<1e-9
    assert abs(elo["HOME"]+elo["DRAW"]+elo["AWAY"]-1)<1e-9
    assert "HOME" in ens and 0<=agr<=1
    assert not any(k in ens for k in ("PLAY","WATCH","PASS"))
    print("EVIDENCE ENGINE SELF-TEST: PASSED")
