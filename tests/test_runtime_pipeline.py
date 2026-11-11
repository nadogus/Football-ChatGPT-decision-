from datetime import datetime, timezone
from football_evidence_engine import scoreline_markets, elo_1x2
from build_match_packet import build_runtime_packet

def test_runtime_packet_has_no_production_decision():
    models={
        "dixon_coles":scoreline_markets(1.8,0.9),
        "elo":elo_1x2(1750,1600),
    }
    odds={
        "primary_source":"flashscore",
        "observed_at":datetime.now(timezone.utc).isoformat(),
        "quotes":[
            {"market":"1X2","selection":"HOME","decimal_odds":1.95,"bookmaker":"bet365"},
            {"market":"1X2","selection":"DRAW","decimal_odds":3.60,"bookmaker":"bet365"},
            {"market":"1X2","selection":"AWAY","decimal_odds":4.50,"bookmaker":"bet365"},
        ],
    }
    sources=[{"source":"understat","observed_at":datetime.now(timezone.utc).isoformat(),"data":{"ok":True}},
             {"source":"clubelo","observed_at":datetime.now(timezone.utc).isoformat(),"data":{"ok":True}}]
    p=build_runtime_packet(match={"match_id":"T1","home":"A","away":"B","competition":"Test","kickoff":"2030-01-01T00:00:00Z"},models=models,source_payloads=sources,odds_payload=odds)
    assert p["decision_authority"]=="AI_REVIEWER_ONLY"
    assert p["production_decision"] is None
    assert p["market"]["model_vs_market"]
    assert all("decision" not in c and "ev" not in c for c in p["market"]["model_vs_market"])

def test_post_xi_stage_only_when_verified():
    models={"dc":scoreline_markets(1.2,1.1)}
    p=build_runtime_packet(match={"match_id":"T2"},models=models,source_payloads=[],odds_payload={"quotes":[]},xi={"official_verified":True})
    assert p["stage"]=="POST_XI"
