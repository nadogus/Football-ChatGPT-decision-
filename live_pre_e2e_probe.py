"""Real PRE end-to-end probe for Liverpool-Arsenal.

Fail closed: this probe never invents model inputs and never assigns a betting decision.
It proves what the automatic runtime can actually collect today and records missing
inputs explicitly when a complete PRE packet cannot yet be built.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from evidence_collector import collect_match_evidence_auto, packet_inputs
from public_sources import UnderstatClient, ClubEloClient

MATCH={
    "home":"Liverpool",
    "away":"Arsenal",
    "kickoff":"2026-11-01T16:30:00+00:00",
    "competition":"English Premier League",
}
SEASON=2026

def main():
    collection=collect_match_evidence_auto(
        match=MATCH,
        espn_league_slug="eng.1",
        pinnacle_league_id=1980,
    )
    inputs=packet_inputs(collection)
    model_inputs={"home_xg":None,"away_xg":None,"home_elo":None,"away_elo":None}
    model_sources={}
    gaps=[]
    try:
        u=UnderstatClient()
        hx=u.team_xg_summary("Liverpool",SEASON,last_n=10)
        ax=u.team_xg_summary("Arsenal",SEASON,last_n=10)
        model_sources["understat"]={"home":hx,"away":ax}
        if hx and ax:
            # Symmetric attack/defence blend; deterministic, not a betting decision.
            model_inputs["home_xg"]=round((float(hx["xg_for"])+float(ax["xg_against"]))/2,4)
            model_inputs["away_xg"]=round((float(ax["xg_for"])+float(hx["xg_against"]))/2,4)
        else:gaps.append("UNDERSTAT_XG_UNAVAILABLE")
    except Exception as e:gaps.append(f"UNDERSTAT_XG_ERROR:{type(e).__name__}")
    try:
        elo=ClubEloClient()
        model_inputs["home_elo"]=elo.latest_elo("Liverpool")
        model_inputs["away_elo"]=elo.latest_elo("Arsenal")
        model_sources["clubelo"]={"home":model_inputs["home_elo"],"away":model_inputs["away_elo"]}
        if model_inputs["home_elo"] is None or model_inputs["away_elo"] is None:gaps.append("CLUBELO_UNAVAILABLE")
    except Exception as e:gaps.append(f"CLUBELO_ERROR:{type(e).__name__}")

    quote_count=len(inputs.get("odds_payload",{}).get("quotes",[]))
    required_ok=all(v is not None for v in model_inputs.values()) and quote_count>0
    packet=None
    if required_ok:
        from match_runner import run_pre
        packet=run_pre(
            match=MATCH,
            home_xg=model_inputs["home_xg"],away_xg=model_inputs["away_xg"],
            home_elo=model_inputs["home_elo"],away_elo=model_inputs["away_elo"],
            source_payloads=inputs["source_payloads"],odds_payload=inputs["odds_payload"],
            context={**inputs["context"],"model_input_sources":model_sources,"real_pre_probe":True},
            ledger_path="ledger/live_pre_e2e.jsonl",
        )
    report={
        "generated_at":datetime.now(timezone.utc).isoformat(),"match":MATCH,
        "collection_status":collection.get("collection_status"),
        "resolution":collection.get("resolution"),
        "model_inputs":model_inputs,"model_sources":model_sources,
        "quote_count":quote_count,"gaps":gaps,
        "status":"PRE_EVIDENCE_READY" if packet else "FAIL_CLOSED_INCOMPLETE_PRE_EVIDENCE",
        "packet":packet,
    }
    with open("LIVE_PRE_E2E.json","w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if packet:
        assert packet.get("event")=="PRE_EVIDENCE_READY"
        assert packet.get("decision_authority")=="CHATGPT_ONLY"
        assert packet.get("production_decision") is None
    return 0

if __name__=="__main__":raise SystemExit(main())
