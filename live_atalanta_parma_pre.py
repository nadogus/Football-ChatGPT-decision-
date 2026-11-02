"""PRE probe for Atalanta-Parma, Serie A, 2026-11-02.
Evidence only; no live betting data and no production decision is assigned.
"""
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from evidence_collector import collect_match_evidence_auto, packet_inputs
from data_adapters import FlashscoreClient, normalize_decimal_quotes
from public_sources import FlashscoreModelClient

MATCH={"home":"Atalanta","away":"Parma","kickoff":"2026-11-02T19:45:00+00:00","competition":"Serie A"}
AS_OF=datetime.fromisoformat(MATCH["kickoff"])
def norm(x):return re.sub(r"[^a-z0-9]+","",str(x or "").lower())
def rating_for(ratings,name):
    target=norm(name)
    aliases={"atalanta":{"atalanta","atalantabc"},"parma":{"parma","parmacalcio1913","parmacalcio"}}
    wanted=aliases.get(target,{target})
    for k,v in ratings.items():
        if norm(k) in wanted:return v
    return None

def main():
    collection=collect_match_evidence_auto(match=MATCH,espn_league_slug="ita.1")
    inputs=packet_inputs(collection)
    fs=FlashscoreModelClient()
    hx=fs.team_xg_summary(MATCH["home"],"Serie A",AS_OF,last_n=8)
    ax=fs.team_xg_summary(MATCH["away"],"Serie A",AS_OF,last_n=8)
    ratings=fs.computed_elo(MATCH["home"],"Serie A",AS_OF)
    he=rating_for(ratings,MATCH["home"]);ae=rating_for(ratings,MATCH["away"])
    model_inputs={"home_xg":None,"away_xg":None,"home_elo":he,"away_elo":ae};gaps=[]
    if hx and ax:
        model_inputs["home_xg"]=round((float(hx["xg_for"])+float(ax["xg_against"]))/2,4)
        model_inputs["away_xg"]=round((float(ax["xg_for"])+float(hx["xg_against"]))/2,4)
    else:gaps.append("FLASHSCORE_XG_UNAVAILABLE")
    if he is None or ae is None:gaps.append("FLASHSCORE_ELO_UNAVAILABLE")
    observed_at=datetime.now(timezone.utc).isoformat()
    prematch_odds={"primary_source":"flashscore","observed_at":observed_at,"quotes":[]}
    fs_match_id=(collection.get("resolution",{}).get("resolved_ids",{}) or {}).get("flashscore_match_id")
    if fs_match_id:
        raw=FlashscoreClient().odds(str(fs_match_id))
        if raw.ok:prematch_odds["quotes"]=normalize_decimal_quotes(raw.data,"flashscore",prefer_opening=False)
    quote_count=len(prematch_odds["quotes"])
    if quote_count==0:gaps.append("PREMATCH_QUOTES_UNAVAILABLE")
    packet=None;extras=[]
    if hx and ax:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"pre_xg":{"home":hx,"away":ax,"as_of":MATCH["kickoff"]}}})
    if he is not None and ae is not None:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"pre_elo":{"home":he,"away":ae,"as_of":MATCH["kickoff"],"league":"Serie A"}}})
    if not gaps:
        from match_runner import run_pre
        packet=run_pre(match=MATCH,home_xg=model_inputs["home_xg"],away_xg=model_inputs["away_xg"],home_elo=he,away_elo=ae,source_payloads=inputs["source_payloads"]+extras,odds_payload=prematch_odds,context={**inputs["context"],"historical_reconstruction":True,"strict_as_of":MATCH["kickoff"],"odds_basis":"flashscore_prematch_snapshot","model_sources":{"flashscore_xg":{"home":hx,"away":ax},"flashscore_elo":{"home":he,"away":ae}}},ledger_path="ledger/atalanta_parma_pre.jsonl")
    report={"generated_at":observed_at,"match":MATCH,"mode":"HISTORICAL_PRE_PROBE","collection_status":collection.get("collection_status"),"resolution":collection.get("resolution"),"model_inputs":model_inputs,"model_sources":{"flashscore_xg":{"home":hx,"away":ax},"flashscore_elo":{"home":he,"away":ae}},"quote_count":quote_count,"gaps":gaps,"status":"PRE_EVIDENCE_READY" if packet else "FAIL_CLOSED_INCOMPLETE_PRE_EVIDENCE","packet":packet}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    with open("ATALANTA_PARMA_PRE.json","w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
    if packet:assert packet["decision_authority"]=="CHATGPT_ONLY" and packet["production_decision"] is None
    return 0
if __name__=="__main__":raise SystemExit(main())
