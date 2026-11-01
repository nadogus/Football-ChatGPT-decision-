"""One-off real system probe for Fenerbahce-Goztepe, 2026-10-31.
Evidence-only validation; never assigns a betting decision.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from evidence_collector import collect_match_evidence_auto, packet_inputs
from public_sources import UnderstatClient, ClubEloClient
from match_runner import run_pre

MATCH={"home":"Fenerbahce","away":"Goztepe","kickoff":"2026-10-31T16:00:00+00:00","competition":"Turkish Super Lig"}
SEASON=2026

def main():
    collection=collect_match_evidence_auto(match=MATCH,espn_league_slug="tur.1")
    inputs=packet_inputs(collection)
    u=UnderstatClient(); observed_at=datetime.now(timezone.utc).isoformat(); gaps=[]; model_sources={}; payloads=[]
    hx=u.team_xg_summary("Fenerbahce",SEASON,last_n=10)
    ax=u.team_xg_summary("Goztepe",SEASON,last_n=10)
    if not (hx and ax):
        hx=hx or u.team_xg_summary("Fenerbahce",SEASON-1,last_n=10)
        ax=ax or u.team_xg_summary("Goztepe",SEASON-1,last_n=10)
    model_sources["understat"]={"home":hx,"away":ax}
    if not (hx and ax): gaps.append("UNDERSTAT_XG_UNAVAILABLE")
    home_xg=round((float(hx["xg_for"])+float(ax["xg_against"]))/2,4) if hx and ax else None
    away_xg=round((float(ax["xg_for"])+float(hx["xg_against"]))/2,4) if hx and ax else None
    as_of=datetime.fromisoformat(MATCH["kickoff"])
    he=ae=None
    try:
        ce=ClubEloClient(); he=ce.latest_elo("Fenerbahce",as_of); ae=ce.latest_elo("Goztepe",as_of)
    except Exception: pass
    if he is None or ae is None:
        try:
            ratings=u.computed_elo("Super_Lig",SEASON,as_of=as_of)
            he=he if he is not None else ratings.get("Fenerbahce") or ratings.get("Fenerbahçe")
            ae=ae if ae is not None else ratings.get("Goztepe") or ratings.get("Göztepe")
            model_sources["understat_elo"]={"home":he,"away":ae,"league":"Super_Lig"}
        except Exception as e: gaps.append(f"ELO_ERROR:{type(e).__name__}")
    if he is None or ae is None: gaps.append("ELO_UNAVAILABLE")
    if hx and ax: payloads.append({"source":"understat","observed_at":observed_at,"data":model_sources})
    quotes=len(inputs.get("odds_payload",{}).get("quotes",[]))
    packet=None
    if all(v is not None for v in [home_xg,away_xg,he,ae]) and quotes:
        packet=run_pre(match=MATCH,home_xg=home_xg,away_xg=away_xg,home_elo=he,away_elo=ae,source_payloads=inputs["source_payloads"]+payloads,odds_payload=inputs["odds_payload"],context={**inputs["context"],"model_input_sources":model_sources,"one_off_probe":True},ledger_path="ledger/fenerbahce_goztepe_probe.jsonl")
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"match":MATCH,"collection_status":collection.get("collection_status"),"resolution":collection.get("resolution"),"model_inputs":{"home_xg":home_xg,"away_xg":away_xg,"home_elo":he,"away_elo":ae},"model_sources":model_sources,"quote_count":quotes,"gaps":gaps,"status":"PRE_EVIDENCE_READY" if packet else "FAIL_CLOSED_INCOMPLETE_PRE_EVIDENCE","packet":packet}
    print(json.dumps(report,ensure_ascii=False,indent=2)); open("FENERBAHCE_GOZTEPE_PROBE.json","w").write(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
