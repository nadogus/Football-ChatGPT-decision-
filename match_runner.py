"""MATCH_RUNNER V1.2
Deterministic orchestration: resolve -> collect evidence -> calculate -> packet -> ledger.
It intentionally stops before the betting decision. ChatGPT is the sole decision authority.
"""
from __future__ import annotations
from typing import Any
from football_evidence_engine import scoreline_markets, elo_1x2, ImmutableLedger
from build_match_packet import build_runtime_packet

RUNNER_VERSION="MATCH_RUNNER_V1.2"

def run_pre(*,match:dict[str,Any],home_xg:float,away_xg:float,home_elo:float,away_elo:float,source_payloads:list[dict[str,Any]],odds_payload:dict[str,Any],league_coverage:float=1.0,context:dict[str,Any]|None=None,ledger_path:str="ledger/evidence.jsonl"):
    models={"dixon_coles":scoreline_markets(home_xg,away_xg),"elo":elo_1x2(home_elo,away_elo)}
    packet=build_runtime_packet(match=match,models=models,source_payloads=source_payloads,odds_payload=odds_payload,league_coverage=league_coverage,xi={"official_verified":False},context={**(context or {}),"runner_version":RUNNER_VERSION},engine_version="evidence-v1.1")
    packet["event"]="PRE_EVIDENCE_READY"
    packet["ledger_sha256"]=ImmutableLedger(ledger_path).append(packet)
    return packet

def run_pre_collected(*,match:dict[str,Any],home_xg:float,away_xg:float,home_elo:float,away_elo:float,
                      provider_ids:dict[str,Any]|None=None,pinnacle_league_id:int|None=None,date_yyyymmdd:str|None=None,
                      odds_league:str|None=None,league_coverage:float=1.0,context:dict[str,Any]|None=None,
                      ledger_path:str="ledger/evidence.jsonl"):
    """Collect configured live sources using already-known provider IDs."""
    from evidence_collector import collect_match_evidence, packet_inputs
    collection=collect_match_evidence(match=match,provider_ids=provider_ids,pinnacle_league_id=pinnacle_league_id,
                                      date_yyyymmdd=date_yyyymmdd,odds_league=odds_league)
    inputs=packet_inputs(collection)
    return run_pre(match=match,home_xg=home_xg,away_xg=away_xg,home_elo=home_elo,away_elo=away_elo,
                   source_payloads=inputs["source_payloads"],odds_payload=inputs["odds_payload"],league_coverage=league_coverage,
                   context={**(context or {}),**inputs["context"]},ledger_path=ledger_path)

def run_pre_auto(*,match:dict[str,Any],home_xg:float,away_xg:float,home_elo:float,away_elo:float,
                 espn_league_slug:str|None=None,fotmob_league_id:int|None=None,pinnacle_league_id:int|None=None,
                 date_yyyymmdd:str|None=None,odds_league:str|None=None,league_coverage:float=1.0,
                 context:dict[str,Any]|None=None,ledger_path:str="ledger/evidence.jsonl"):
    """Resolve provider IDs from the fixture, collect evidence, then build PRE packet.

    Resolution is fail-closed. Weak/ambiguous matches remain unresolved and are recorded
    in packet.context.fixture_resolution rather than guessed.
    """
    from evidence_collector import collect_match_evidence_auto, packet_inputs
    collection=collect_match_evidence_auto(
        match=match,
        espn_league_slug=espn_league_slug,
        fotmob_league_id=fotmob_league_id,
        pinnacle_league_id=pinnacle_league_id,
        date_yyyymmdd=date_yyyymmdd,
        odds_league=odds_league,
    )
    inputs=packet_inputs(collection)
    return run_pre(
        match=match,home_xg=home_xg,away_xg=away_xg,home_elo=home_elo,away_elo=away_elo,
        source_payloads=inputs["source_payloads"],odds_payload=inputs["odds_payload"],league_coverage=league_coverage,
        context={**(context or {}),**inputs["context"]},ledger_path=ledger_path,
    )

def run_post_xi(*,match:dict[str,Any],repriced_models:dict[str,dict[str,float]],source_payloads:list[dict[str,Any]],odds_payload:dict[str,Any],xi:dict[str,Any],league_coverage:float=1.0,context:dict[str,Any]|None=None,ledger_path:str="ledger/evidence.jsonl"):
    if not xi.get("official_verified"):raise ValueError("POST_XI requires official_verified=true")
    packet=build_runtime_packet(match=match,models=repriced_models,source_payloads=source_payloads,odds_payload=odds_payload,league_coverage=league_coverage,xi=xi,context={**(context or {}),"runner_version":RUNNER_VERSION,"full_repricing":True},engine_version="evidence-v1.1")
    packet["event"]="POST_XI_EVIDENCE_READY"
    packet["ledger_sha256"]=ImmutableLedger(ledger_path).append(packet)
    return packet

if __name__=="__main__":print(f"{RUNNER_VERSION}: READY")
