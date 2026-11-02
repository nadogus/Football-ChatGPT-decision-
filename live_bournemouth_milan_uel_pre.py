"""Historical PRE probe: Bournemouth-Milan, UEFA Europa League, 2026-10-22."""
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from evidence_collector import collect_match_evidence_auto, packet_inputs
from data_adapters import FlashscoreClient, normalize_decimal_quotes
from public_sources import FlashscoreModelClient
MATCH={"home":"Bournemouth","away":"Milan","kickoff":"2026-10-22T19:00:00+00:00","competition":"Europa League"};AS_OF=datetime.fromisoformat(MATCH["kickoff"])
def norm(x):return re.sub(r"[^a-z0-9]+","",str(x or "").lower())
def rating_for(ratings,name):
 aliases={"bournemouth":{"bournemouth","afcbournemouth"},"milan":{"milan","acmilan"}};wanted=aliases.get(norm(name),{norm(name)})
 for k,v in ratings.items():
  if norm(k) in wanted:return v
 return None
def main():
 collection=collect_match_evidence_auto(match=MATCH,espn_league_slug="uefa.europa");inputs=packet_inputs(collection);fs=FlashscoreModelClient();hx=fs.team_xg_summary(MATCH["home"],"Europa League",AS_OF,last_n=8);ax=fs.team_xg_summary(MATCH["away"],"Europa League",AS_OF,last_n=8);ratings=fs.computed_elo(MATCH["home"],"Europa League",AS_OF);he=rating_for(ratings,MATCH["home"]);ae=rating_for(ratings,MATCH["away"]);gaps=[];mi={"home_xg":None,"away_xg":None,"home_elo":he,"away_elo":ae}
 if hx and ax:mi["home_xg"]=round((float(hx["xg_for"])+float(ax["xg_against"]))/2,4);mi["away_xg"]=round((float(ax["xg_for"])+float(hx["xg_against"]))/2,4)
 else:gaps.append("FLASHSCORE_XG_UNAVAILABLE")
 if he is None or ae is None:gaps.append("FLASHSCORE_ELO_UNAVAILABLE")
 observed_at=datetime.now(timezone.utc).isoformat();odds={"primary_source":"flashscore","observed_at":observed_at,"quotes":[]};mid=(collection.get("resolution",{}).get("resolved_ids",{}) or {}).get("flashscore_match_id")
 if mid:
  raw=FlashscoreClient().odds(str(mid));odds["quotes"]=normalize_decimal_quotes(raw.data,"flashscore",prefer_opening=False) if raw.ok else []
 if not odds["quotes"]:gaps.append("PREMATCH_QUOTES_UNAVAILABLE")
 packet=None;extras=[]
 if hx and ax:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"pre_xg":{"home":hx,"away":ax,"as_of":MATCH["kickoff"]}}})
 if he is not None and ae is not None:extras.append({"source":"flashscore","observed_at":observed_at,"data":{"pre_elo":{"home":he,"away":ae,"as_of":MATCH["kickoff"],"league":"Europa League"}}})
 if not gaps:
  from match_runner import run_pre
  packet=run_pre(match=MATCH,home_xg=mi["home_xg"],away_xg=mi["away_xg"],home_elo=he,away_elo=ae,source_payloads=inputs["source_payloads"]+extras,odds_payload=odds,context={**inputs["context"],"historical_reconstruction":True,"strict_as_of":MATCH["kickoff"],"odds_basis":"flashscore_prematch_snapshot"},ledger_path="ledger/bournemouth_milan_uel_pre.jsonl")
 report={"generated_at":observed_at,"match":MATCH,"mode":"HISTORICAL_PRE_PROBE","collection_status":collection.get("collection_status"),"resolution":collection.get("resolution"),"model_inputs":mi,"quote_count":len(odds["quotes"]),"gaps":gaps,"status":"PRE_EVIDENCE_READY" if packet else "FAIL_CLOSED_INCOMPLETE_PRE_EVIDENCE","packet":packet};print(json.dumps(report,ensure_ascii=False,indent=2));json.dump(report,open("BOURNEMOUTH_MILAN_UEL_PRE.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
 if packet:assert packet["decision_authority"]=="CHATGPT_ONLY" and packet["production_decision"] is None
if __name__=="__main__":main()
