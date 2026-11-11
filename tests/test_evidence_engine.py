from datetime import datetime, timezone, timedelta
from football_evidence_engine import *

def test_probabilities_and_no_decision():
    dc=scoreline_markets(1.7,1.1)
    elo=elo_1x2(1720,1640)
    combined,agreement=ensemble([dc,elo])
    assert abs(dc['HOME']+dc['DRAW']+dc['AWAY']-1)<1e-9
    assert 0<=agreement<=1
    assert all(x not in combined for x in ('PLAY','WATCH','PASS'))

def test_staleness_is_evidence_not_final_decision():
    s=SourceDatum('pinnacle',datetime.now(timezone.utc)-timedelta(hours=1),.92,600,{})
    x=integrity([s])
    assert 'STALE:pinnacle' in x['flags']
    assert 'decision' not in x

def test_model_vs_market_has_no_ev_ranking_or_decision():
    now=datetime.now(timezone.utc)
    quotes=[MarketQuote('1X2','HOME',2.0,'A',now),MarketQuote('1X2','DRAW',3.4,'A',now),MarketQuote('1X2','AWAY',4.0,'A',now)]
    rows=model_vs_market({'HOME':.55,'DRAW':.25,'AWAY':.20},quotes)
    assert [r['selection'] for r in rows]==['HOME','DRAW','AWAY']
    assert all(k not in r for r in rows for k in ('decision','ev','edge_pp','fair_odds'))
    assert all(r['model_minus_market_pp'] is not None for r in rows)

def test_integrity_has_no_numeric_score():
    now=datetime.now(timezone.utc)
    x=integrity([SourceDatum('flashscore',now,.8,900,{})])
    assert 'data_quality' not in x and x['sources']==['flashscore'] and x['stale_sources']==[]

def test_packet_authority():
    now=datetime.now(timezone.utc)
    sources=[SourceDatum('sofascore:event',now,.82,21600,{})]
    quotes=[MarketQuote('1X2','HOME',2.0,'A',now),MarketQuote('1X2','DRAW',3.4,'A',now),MarketQuote('1X2','AWAY',4.0,'A',now)]
    p=build_evidence_packet(match={'id':'x','home':'H','away':'A'},sources=sources,league_coverage=1.0,
        models={'dc':scoreline_markets(1.6,1.0),'elo':elo_1x2(1700,1600)},quotes=quotes)
    assert p['decision_authority']=='AI_REVIEWER_ONLY'
    assert p['production_decision'] is None
