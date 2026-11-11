"""Deterministic evidence engine. Calculates evidence; NEVER assigns PLAY/WATCH/PASS.
The decision is made by the AI reviewer under CHATGPT_DECISION_POLICY.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json, math, statistics, hashlib
from pathlib import Path
@dataclass
class SourceDatum:
    source:str;observed_at:datetime;reliability:float;max_age_seconds:int;payload:dict[str,Any]=field(default_factory=dict)
    def age_seconds(self,now=None):
        now=now or datetime.now(timezone.utc);t=self.observed_at if self.observed_at.tzinfo else self.observed_at.replace(tzinfo=timezone.utc);return max(0.0,(now-t).total_seconds())
    def fresh(self,now=None):return self.age_seconds(now)<=self.max_age_seconds
@dataclass
class MarketQuote:
    market:str;selection:str;decimal_odds:float;bookmaker:str;observed_at:datetime;phase:str="CURRENT"
    def __post_init__(self):
        if self.decimal_odds<=1:raise ValueError("decimal_odds must be > 1")
SOURCE_POLICY={"sofascore:event":(.82,21600),"sofascore:lineups":(.88,1800),"understat":(.86,86400),"clubelo":(.90,86400),"espn":(.80,7200),"flashscore":(.80,900),"flashscore:odds":(.80,900),"fotmob":(.80,21600),"open-meteo":(.80,21600)}
def integrity(sources:list[SourceDatum],league_coverage:float=1.0,now=None):
    """Which sources are present and which are stale. No numeric 'quality score':
    the old weighted score rested on hand-picked reliability constants with no empirical basis."""
    if not sources:return {"sources":[],"stale_sources":[],"league_coverage":league_coverage,"flags":["NO_SOURCE_DATA"]}
    stale=sorted({d.source for d in sources if not d.fresh(now)});flags=[f"STALE:{x}" for x in stale]
    if league_coverage<.70:flags.append("LOW_LEAGUE_COVERAGE")
    return {"sources":sorted({d.source for d in sources}),"stale_sources":stale,"league_coverage":league_coverage,"flags":sorted(set(flags))}
def poisson_pmf(k,lam):return math.exp(-lam)*(lam**k)/math.factorial(k)
def dc_tau(h,a,hx,ax,rho=-.08):
    if h==0 and a==0:return 1-(hx*ax*rho)
    if h==0 and a==1:return 1+(hx*rho)
    if h==1 and a==0:return 1+(ax*rho)
    if h==1 and a==1:return 1-rho
    return 1.0
def score_matrix(home_xg,away_xg,max_goals=8,rho=-.08):
    m={};total=0.0
    for h in range(max_goals+1):
        for a in range(max_goals+1):
            p=poisson_pmf(h,home_xg)*poisson_pmf(a,away_xg)*dc_tau(h,a,home_xg,away_xg,rho);m[(h,a)]=max(0,p);total+=m[(h,a)]
    return {k:v/total for k,v in m.items()}
def scoreline_markets(home_xg,away_xg):
    m=score_matrix(home_xg,away_xg);home=sum(p for (h,a),p in m.items() if h>a);draw=sum(p for (h,a),p in m.items() if h==a);away=1-home-draw;btts=sum(p for (h,a),p in m.items() if h>0 and a>0);over25=sum(p for (h,a),p in m.items() if h+a>=3)
    return {"HOME":home,"DRAW":draw,"AWAY":away,"BTTS_YES":btts,"OVER_2.5":over25,"UNDER_2.5":1-over25,"HOME_DNB":home/(home+away) if home+away else .5,"AWAY_DNB":away/(home+away) if home+away else .5,"1X":home+draw,"X2":away+draw}
def elo_1x2(home_elo,away_elo,home_advantage=65.0,draw_base=.25):
    diff=(home_elo+home_advantage)-away_elo;non_draw_home=1/(1+10**(-diff/400));draw=max(.12,min(.32,draw_base*math.exp(-abs(diff)/900)));return {"HOME":(1-draw)*non_draw_home,"DRAW":draw,"AWAY":(1-draw)*(1-non_draw_home)}
def ensemble(models,weights=None):
    if not models:return {},0.0
    weights=weights or [1.0]*len(models);keys=set().union(*(m.keys() for m in models));out={}
    for k in keys:
        pairs=[(m[k],w) for m,w in zip(models,weights) if k in m];out[k]=sum(v*w for v,w in pairs)/sum(w for _,w in pairs)
    vals=[]
    for k in ("HOME","DRAW","AWAY"):
        xs=[m[k] for m in models if k in m]
        if len(xs)>1:vals.append(statistics.pstdev(xs))
    dispersion=sum(vals)/len(vals) if vals else 0.0;return out,max(0.0,min(1.0,1-dispersion/.18))
def proportional_devig(decimal_odds):
    raw={k:1/v for k,v in decimal_odds.items()};z=sum(raw.values());return {k:v/z for k,v in raw.items()}
def fair_odds(p):return None if p<=0 else 1/p
def best_prices(quotes):
    best={}
    for q in quotes:
        if str(getattr(q,"phase","CURRENT")).upper()!="CURRENT":continue  # opening/closing quotes are not bettable prices
        key=(q.market,q.selection)
        if key not in best or q.decimal_odds>best[key].decimal_odds:best[key]=q
    return best
def market_consensus(quotes,market):
    from market_evidence import canonical_market
    books={};want=canonical_market(market)
    for q in quotes:
        if canonical_market(q.market)==want and str(getattr(q,"phase","CURRENT")).upper()=="CURRENT":books.setdefault(q.bookmaker,{})[q.selection]=q.decimal_odds
    probs=[proportional_devig(odds) for odds in books.values() if len(odds)>=2];keys=set().union(*(p.keys() for p in probs)) if probs else set();return {k:sum(p.get(k,0) for p in probs)/len(probs) for k in keys} if probs else {}
def movement(opening,current):return current/opening-1
CORRELATION_FAMILY={"HOME":"HOME_SIDE","HOME_ML":"HOME_SIDE","HOME_DNB":"HOME_SIDE","HOME_-0.25":"HOME_SIDE","HOME_-0.5":"HOME_SIDE","AWAY":"AWAY_SIDE","AWAY_ML":"AWAY_SIDE","AWAY_DNB":"AWAY_SIDE","AWAY_+0.25":"AWAY_SIDE","AWAY_+0.5":"AWAY_SIDE","UNDER_2.5":"TOTAL_UNDER","UNDER_3.0":"TOTAL_UNDER","UNDER_3.5":"TOTAL_UNDER","OVER_2.5":"TOTAL_OVER","OVER_3.0":"TOTAL_OVER","OVER_3.5":"TOTAL_OVER"}
def model_vs_market(probabilities,quotes,market=None):
    """Model probability next to the vig-free market probability, per selection.

    Deliberately NOT ranked by model EV and carries no edge/EV field: these models
    (xG average, season Elo, Dixon-Coles family) did not beat the closing line in the
    2019-2026 backtest, so a large model-vs-market gap is more often model error than value."""
    from market_evidence import market_fair_probability,market_summary
    market=market or market_summary(quotes);best=best_prices(quotes);rows=[]
    order={"HOME":0,"DRAW":1,"AWAY":2}
    for (market_name,selection),q in sorted(best.items(),key=lambda kv:(order.get(kv[0][1],9),kv[0][1])):
        if selection not in probabilities:continue
        mp=market_fair_probability(market,selection)
        if mp is None:continue
        p=probabilities[selection]
        rows.append({"market":market_name,"selection":selection,"model_probability":round(p,4),"market_fair_probability":mp,"model_minus_market_pp":round(100*(p-mp),2),"best_odds":q.decimal_odds,"bookmaker":q.bookmaker,"correlation_family":CORRELATION_FAMILY.get(selection,selection)})
    return rows
def build_evidence_packet(*,match,sources,league_coverage,models,quotes,xi=None,context=None,engine_version="evidence-v1.0"):
    integ=integrity(sources,league_coverage);combined,agreement=ensemble(list(models.values()));return {"schema_version":"1.0","engine_version":engine_version,"generated_at":datetime.now(timezone.utc).isoformat(),"match":match,"stage":"POST_XI" if (xi or {}).get("official_verified") else "PRE","integrity":integ,"source_evidence":[{"source":s.source,"observed_at":s.observed_at.isoformat(),"fresh":s.fresh()} for s in sources],"models":{"individual":models,"ensemble":combined,"model_agreement":round(agreement,4)},"market":_market_section(quotes,combined),"xi":xi or {"official_verified":False},"context":context or {},"decision_authority":"AI_REVIEWER_ONLY","production_decision":None,"warnings":integ["flags"]}
def _market_section(quotes,combined):
    from market_evidence import market_summary
    summary=market_summary(quotes)
    return {"consensus_1x2":(summary.get("1x2") or {}).get("consensus_fair") or {},"summary":summary,"model_vs_market":model_vs_market(combined,quotes,summary)}
class ImmutableLedger:
    def __init__(self,path="ledger/evidence.jsonl"):self.path=Path(path)
    def append(self,packet):
        self.path.parent.mkdir(parents=True,exist_ok=True);raw=json.dumps(packet,sort_keys=True,separators=(",",":"),default=str);record={"sha256":hashlib.sha256(raw.encode()).hexdigest(),"packet":packet}
        with self.path.open("a",encoding="utf-8") as f:f.write(json.dumps(record,ensure_ascii=False,default=str)+"\n")
        return record["sha256"]
if __name__=="__main__":
    dc=scoreline_markets(1.65,1.05);elo=elo_1x2(1700,1620);ens,agr=ensemble([dc,elo]);assert abs(dc["HOME"]+dc["DRAW"]+dc["AWAY"]-1)<1e-9;assert abs(elo["HOME"]+elo["DRAW"]+elo["AWAY"]-1)<1e-9;assert "HOME" in ens and 0<=agr<=1;assert not any(k in ens for k in ("PLAY","WATCH","PASS"));print("EVIDENCE ENGINE SELF-TEST: PASSED")
