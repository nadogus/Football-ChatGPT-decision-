"""POST-XI evidence runtime for Football ChatGPT Decision.
Evidence only. This module never assigns PLAY/WATCH/PASS.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class PlayerImpact:
    player_id: str
    name: str
    position: str = "UNK"
    attack: float = 0.0
    creation: float = 0.0
    progression: float = 0.0
    defence: float = 0.0
    pressing: float = 0.0
    aerial: float = 0.0
    set_piece: float = 0.0
    goalkeeper: float = 0.0
    minutes_reliability: float = 1.0
    data_quality: float = 1.0

    def score(self) -> float:
        if self.position.upper() in {"GK", "GOALKEEPER"}:
            base = 0.80*self.goalkeeper + 0.20*self.progression
        else:
            base = (0.28*self.attack + 0.20*self.creation + 0.12*self.progression +
                    0.18*self.defence + 0.10*self.pressing + 0.05*self.aerial + 0.07*self.set_piece)
        return base * max(0.0,min(1.0,self.minutes_reliability)) * max(0.0,min(1.0,self.data_quality))

def xi_delta(expected_ids:list[str], official_ids:list[str], impacts:dict[str,PlayerImpact]) -> dict[str,Any]:
    expected=set(map(str,expected_ids)); official=set(map(str,official_ids))
    missing=sorted(expected-official); unexpected=sorted(official-expected)
    missing_loss=sum(impacts[p].score() for p in missing if p in impacts)
    incoming_gain=sum(impacts[p].score() for p in unexpected if p in impacts)
    gk_changes=[p for p in missing+unexpected if p in impacts and impacts[p].position.upper() in {"GK","GOALKEEPER"}]
    return {
        "missing_expected":missing,
        "unexpected_starters":unexpected,
        "missing_strength":round(missing_loss,6),
        "incoming_strength":round(incoming_gain,6),
        "net_strength_delta":round(incoming_gain-missing_loss,6),
        "goalkeeper_changes":gk_changes,
    }

def post_xi_context(*,expected_home:list[str],expected_away:list[str],official_home:list[str],official_away:list[str],impacts:dict[str,PlayerImpact],formation_home:str|None=None,formation_away:str|None=None,validator_count:int=0,reliability:float=0.0):
    return {
        "official_verified":True,
        "validator_count":validator_count,
        "reliability":reliability,
        "home":xi_delta(expected_home,official_home,impacts),
        "away":xi_delta(expected_away,official_away,impacts),
        "formations":{"home":formation_home,"away":formation_away},
        "requires_full_repricing":True,
        "decision_authority":"CHATGPT_ONLY",
    }
