from pathlib import Path
from post_xi_runtime import PlayerImpact, xi_delta, post_xi_context
from ledger import PilotLedger
from pilot_50 import PilotRow, metrics

def test_xi_delta_and_post_xi_contract():
    impacts={"1":PlayerImpact("1","GK","GK",goalkeeper=.8),"2":PlayerImpact("2","A",attack=.7),"3":PlayerImpact("3","B",attack=.5)}
    d=xi_delta(["1","2"],["1","3"],impacts)
    assert d["missing_expected"]==["2"]
    assert d["unexpected_starters"]==["3"]
    x=post_xi_context(expected_home=["1","2"],expected_away=[],official_home=["1","3"],official_away=[],impacts=impacts)
    assert x["official_verified"] is True
    assert x["requires_full_repricing"] is True
    assert x["decision_authority"]=="CHATGPT_ONLY"

def test_ledger_is_append_only(tmp_path):
    p=tmp_path/"pilot.jsonl"; l=PilotLedger(str(p))
    l.append("PRE_DECISION","M1",{"decision":"WATCH"})
    l.append("FINAL_DECISION","M1",{"decision":"PASS"})
    assert len(p.read_text().strip().splitlines())==2

def test_pilot_metrics():
    rows=[PilotRow("1",final_decision="PLAY",result="WIN",pnl_units=1.0,final_price=2.0,closing_price=1.9),PilotRow("2",final_decision="PASS",result="LOSS")]
    m=metrics(rows)
    assert m["target"]==50 and m["plays"]==1 and m["play_hit_rate"]==1.0
