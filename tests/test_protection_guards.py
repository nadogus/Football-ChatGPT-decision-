from datetime import datetime, timezone, timedelta
import pytest
from source_pipeline import verify_official_xi
from match_runner import run_post_xi
from football_evidence_engine import SourceDatum, integrity


def _starters(n=22, confirmed=False):
    return {"confirmed":confirmed,"players":[{"id":i,"starter":True} for i in range(n)]}


def test_nonempty_lineup_is_not_official_xi():
    proof=verify_official_xi({"players":[{"id":1,"name":"Player"}]},[])
    assert proof["verified"] is False


def test_predicted_or_partial_xi_fails_closed():
    proof=verify_official_xi(_starters(11,False),[])
    assert proof["verified"] is False


def test_full_explicit_confirmed_xi_passes():
    proof=verify_official_xi(_starters(22,True),[])
    assert proof["verified"] is True


def test_full_xi_with_independent_validator_passes():
    proof=verify_official_xi(_starters(22,False),[[str(i) for i in range(11)]])
    assert proof["verified"] is True


def test_stale_source_is_flagged():
    d=SourceDatum("pinnacle",datetime.now(timezone.utc)-timedelta(hours=2),.92,600,{})
    out=integrity([d],1.0)
    assert "STALE:pinnacle" in out["flags"]


def test_post_xi_runner_rejects_unverified_xi(tmp_path):
    with pytest.raises(ValueError):
        run_post_xi(match={"id":"x"},repriced_models={"m":{"HOME":.4,"DRAW":.3,"AWAY":.3}},source_payloads=[],odds_payload={"quotes":[]},xi={"official_verified":False},ledger_path=str(tmp_path/"ledger.jsonl"))
