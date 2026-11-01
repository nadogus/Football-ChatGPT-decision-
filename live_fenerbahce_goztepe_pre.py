"""Historical PRE reconstruction probe for Fenerbahce-Goztepe.

Uses only evidence timestamped before kickoff for model inputs.
No production betting decision is assigned.
"""
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from evidence_collector import collect_match_evidence_auto, packet_inputs
from data_adapters import FlashscoreClient, normalize_decimal_quotes
from public_sources import FlashscoreModelClient

MATCH={
    "home":"Fenerbahce",
    "away":"Goztepe",
    "kickoff":"2026-10-31T16:00:00+00:00",
    "competition":"Turkish Super Lig",
}
AS_OF=datetime.fromisoformat(MATCH["kickoff"])

def norm(x):return re.sub(r"[^a-z0-9]+","",str(x or "").lower())
def rating_for(ratings,name):
    target=norm(name)
    for k,v in ratings.items():
        if norm(k)==target:return v
    return None

def main():
    collection=collect_match_evidence_auto(match=MATCH,espn_league_slug="tur.1")
    inputs=packet_inputs(collection)
    fs=FlashscoreModelClient()
    hx=fs.team_xg_summary("Fenerbahce","Super Lig",AS_OF,last_n=8)
    ax=fs.team_xg_summary("Goztepe","Super Lig",AS_OF,last_n=8)
    ratings=fs.computed_elo("Fenerbahce","Super Lig",AS_OF)
    he=rating_for(ratings,"Fenerbahce");ae=rating_for(ratings,"Goztepe")
    model_inputs={"home_xg":None,"away_xg":None,"home_elo":he,"away_elo":ae}
    gaps=[]
    if hx and ax:
        model_inputs["home_xg"]=round((float(hx["xg_for"])+float(ax["xg_against"]))/2,4)
        model_inputs["away_xg"]=round((float(ax["xg_for"])+float(hx["xg_against"]))/2,4)
    else:gaps.append("FLASHSCORE_XG_UNAVAILABLE")
    if he is None or ae is None:gaps.append("FLASHSCORE_ELO_UNAVAILABLE")
    archived_odds={"primary_source":"flashscore","observed_at":MATCH["kickoff"],"quotes":[]}
    fs_match_id=(collection.get("resolution",{}).get("resolved_ids",{}) or {}).get("flashscore_match_id")
    if fs_match_id:
        raw=FlashscoreClient().odds(str(fs_match_id))
        if raw.ok:
            archived_odds["quotes"]=normalize_decimal_quotes(raw.data,"flashscore",prefer_opening=True)
    quote_count=len(archived_odds.get("quotes",[]))
    if quote_count==0:gaps.append("PREMATCH_QUOTES_UNAVAILABLE")
    observed_at=datetime.now(timezone.utc).isoformat()
    extras=[]
    if hx and ax:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"historical_pre_xg":{"home":hx,"away":ax,"as_of":MATCH["kickoff"]}}})
    if he is not None and ae is not None:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"historical_pre_elo":{"home":he,"away":ae,"as_of":MATCH["kickoff"],"league":"Super Lig"}}})
    packet=None
    if not gaps:
        from match_runner import run_pre
        packet=run_pre(
            match=MATCH,
            home_xg=model_inputs["home_xg"],away_xg=model_inputs["away_xg"],
            home_elo=he,away_elo=ae,
            source_payloads=inputs["source_payloads"]+extras,
            odds_payload=archived_odds,
            context={**inputs["context"],"historical_reconstruction":True,"strict_as_of":MATCH["kickoff"],"odds_basis":"flashscore_opening_archive","model_sources":{"flashscore_xg":{"home":hx,"away":ax},"flashscore_elo":{"home":he,"away":ae}}},
            ledger_path="ledger/fenerbahce_goztepe_pre.jsonl",
        )
    report={
        "generated_at":observed_at,
        "match":MATCH,
        "mode":"HISTORICAL_PRE_RECONSTRUCTION",
        "collection_status":collection.get("collection_status"),
        "resolution":collection.get("resolution"),
        "model_inputs":model_inputs,
        "model_sources":{"flashscore_xg":{"home":hx,"away":ax},"flashscore_elo":{"home":he,"away":ae}},
        "quote_count":quote_count,
        "gaps":gaps,
        "status":"PRE_EVIDENCE_READY" if packet else "FAIL_CLOSED_INCOMPLETE_PRE_EVIDENCE",
        "packet":packet,
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    with open("FENERBAHCE_GOZTEPE_PRE.json","w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
    if packet:
        assert packet["decision_authority"]=="CHATGPT_ONLY"
        assert packet["production_decision"] is None
    return 0

if __name__=="__main__":raise SystemExit(main())
