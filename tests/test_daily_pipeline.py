import json
from datetime import datetime, timedelta, timezone

import pytest

import daily_pipeline as dp
from data_adapters import AdapterResult

KICK = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)


def odds_payload(h=2.1, d=3.4, a=3.6):
    return {"markets": [
        {"bookmaker": {"name": "bet365"}, "bet_type": "HOME_DRAW_AWAY", "bet_scope": "FULL_TIME",
         "selections": [{"selection": "home", "value": h, "opening_value": 2.3},
                        {"selection": "draw", "value": d, "opening_value": 3.3},
                        {"selection": "away", "value": a, "opening_value": 3.2}]}]}


class FakeFS:
    base = "http://fake"

    def __init__(self, status="scheduled", score=(None, None)):
        self.status, self.score = status, score

    def matches(self, sport="football", date=None):
        mk = lambda mid, h, a: {"id": mid, "home": {"name": h, "id": "t" + h}, "away": {"name": a, "id": "t" + a},
                                "start_time": KICK.isoformat(), "status": self.status,
                                "home_score": self.score[0], "away_score": self.score[1]}
        return AdapterResult("flashscore", True, {"competitions": [
            {"competition": {"name": "Premier League", "category": "England"}, "matches": [mk("m1", "Liverpool", "Arsenal")]},
            {"competition": {"name": "Bundesliga", "category": "Austria"}, "matches": [mk("m2", "Rapid", "Sturm")]},
            {"competition": {"name": "Premier League Women", "category": "England"}, "matches": [mk("m3", "A", "B")]},
        ]})

    def odds(self, match_id, geo=None):
        return AdapterResult("flashscore", True, odds_payload())

    def missing_players(self, match_id):
        return AdapterResult("flashscore", True, {"home": [{"player": {"name": "X"}, "reason": "Injury", "likelihood": "Doubtful"}], "away": []})

    def _get(self, path, params):
        return AdapterResult("flashscore", False, {}, "NO")


def test_league_filter_rejects_wrong_country_and_women():
    lg = dp.load_leagues()
    assert dp.league_match({"name": "Premier League", "category": "England"}, lg)
    assert not dp.league_match({"name": "Bundesliga", "category": "Austria"}, lg)
    assert not dp.league_match({"name": "Premier League Women", "category": "England"}, lg)
    assert not dp.league_match({"name": "Premier League", "category": "Egypt"}, lg)


def test_scan_marks_gaps_and_never_decides(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "leagues.json").write_text(json.dumps({"leagues": [{"category": "England", "name": "Premier League"}]}))
    sc = dp.Scanner(FakeFS(), pause=0)
    sc.fotmob = type("F", (), {"resolve": lambda self, fx: {"resolved": False, "reason": "TEST"}})()
    monkeypatch.setattr(sc.model, "team_xg_summary", lambda *a, **k: None)
    monkeypatch.setattr(sc.model, "computed_elo", lambda *a, **k: {})
    monkeypatch.setattr(dp, "Scanner", lambda: sc)
    dp.cmd_scan("2026-11-11")
    fx = json.loads((tmp_path / "daily/2026-11-11/fixtures.json").read_text())
    assert [f["match_id"] for f in fx] == ["m1"]
    p = json.loads((tmp_path / "daily/2026-11-11/packets/m1.json").read_text())
    assert p["production_decision"] is None and p["decision_authority"] == "CHATGPT_ONLY"
    assert {"XG_UNAVAILABLE", "ELO_UNAVAILABLE"} <= set(p["context"]["data_gaps"])
    assert p["market"]["summary"]["1x2"]["movement_pp"]["HOME"] > 0
    ozet = (tmp_path / "daily/2026-11-11/OZET.md").read_text()
    assert "Liverpool – Arsenal" in ozet and "Eksik veri" in ozet and "X (Injury; Doubtful)" in ozet
    for word in ("PLAY", "WATCH"):
        assert word not in ozet


def test_record_refuses_after_kickoff_and_settle_computes_clv(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    day = tmp_path / "daily/2026-11-11"
    day.mkdir(parents=True)
    fx = [{"match_id": "m1", "home": "Liverpool", "away": "Arsenal", "kickoff": KICK.isoformat()}]
    (day / "fixtures.json").write_text(json.dumps(fx))
    ns = lambda **k: type("A", (), {**dict(match_id="m1", decision="PLAY", market="1X2", selection="HOME", price=2.30,
                                         bookmaker="bet365", stake=1.0, decided_by="test", note=""), **k})()
    dp.cmd_record(ns())
    dp.cmd_record(ns(decision="PASS", selection="", price=None))
    past = [{**fx[0], "kickoff": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}]
    (day / "fixtures.json").write_text(json.dumps(past))
    with pytest.raises(SystemExit):
        dp.cmd_record(ns())
    # settle: match finished 2-1, closing bet365 2.10/3.40/3.60
    monkeypatch.setattr(dp, "FlashscoreClient", lambda: FakeFS("finished", (2, 1)))
    monkeypatch.setattr(dp.time, "sleep", lambda s: None)
    dp.cmd_settle("2026-11-11")
    s = [json.loads(l) for l in (tmp_path / "decisions/settlements.jsonl").read_text().splitlines()]
    assert len(s) == 2 and s[1]["result"] == "NO_SELECTION" and s[1]["pnl_units"] == 0
    s = [x for x in s if x["decision"] == "PLAY"]
    assert s[0]["result"] == "WIN" and s[0]["pnl_units"] == pytest.approx(1.30)
    assert s[0]["clv"] > 0  # 2.30 taken vs ~2.2 fair at close
    dp.cmd_settle("2026-11-11")  # idempotent
    assert len((tmp_path / "decisions/settlements.jsonl").read_text().splitlines()) == 2
    dp.cmd_report()
    assert "ortalama CLV" in (tmp_path / "decisions/REPORT.md").read_text()


def test_outcomes():
    assert dp.outcome("1X2", "DRAW", 1, 1)[0] == "WIN"
    assert dp.outcome("TOTAL", "OVER_2.5", 2, 1)[0] == "WIN"
    assert dp.outcome("TOTAL", "UNDER_3", 2, 1)[0] == "PUSH"
    assert dp.outcome("DNB", "AWAY_DNB", 0, 0)[0] == "PUSH"
