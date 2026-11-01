"""50-match forward pilot tracker.
Compares ChatGPT Decision with an optional legacy shadow benchmark. No outcome leakage.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

PILOT_TARGET=50

@dataclass
class PilotRow:
    match_id:str
    pre_decision:str|None=None
    final_decision:str|None=None
    final_market:str|None=None
    final_selection:str|None=None
    final_price:float|None=None
    legacy_shadow_decision:str|None=None
    result:str|None=None
    pnl_units:float|None=None
    closing_price:float|None=None

def metrics(rows:list[PilotRow])->dict[str,Any]:
    settled=[r for r in rows if r.result is not None]
    plays=[r for r in settled if r.final_decision=="PLAY"]
    wins=[r for r in plays if r.result=="WIN"]
    pnl=sum(r.pnl_units or 0.0 for r in plays)
    clv=[]
    for r in plays:
        if r.final_price and r.closing_price and r.final_price>1 and r.closing_price>1:
            clv.append((r.final_price/r.closing_price)-1)
    return {
        "target":PILOT_TARGET,
        "recorded":len(rows),
        "settled":len(settled),
        "plays":len(plays),
        "play_hit_rate":len(wins)/len(plays) if plays else None,
        "roi_units_per_play":pnl/len(plays) if plays else None,
        "mean_price_clv":sum(clv)/len(clv) if clv else None,
        "decision_distribution":{k:sum(r.final_decision==k for r in rows) for k in ("PLAY","WATCH","PASS")},
    }
