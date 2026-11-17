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
    pl = [{"category": "Europe", "name": "UEFA Nations League", "match": "prefix"}]
    assert dp.league_match({"name": "UEFA Nations League - League A", "category": "Europe"}, pl)
    assert not dp.league_match({"name": "UEFA Nations League Women", "category": "Europe"}, pl)


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
    assert p["production_decision"] is None and p["decision_authority"] == "AI_REVIEWER_ONLY"
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


def test_stop_rule_blocks_play_after_50_negative_clv(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    day = tmp_path / "daily/2026-11-11"; day.mkdir(parents=True)
    (day / "fixtures.json").write_text(json.dumps([{"match_id": "m1", "home": "A", "away": "B", "kickoff": KICK.isoformat()}]))
    for i in range(50):
        dp.append_jsonl(tmp_path / "decisions/settlements.jsonl", {"decision_id": str(i), "decision": "PLAY", "result": "LOSE", "pnl_units": -1, "stake": 1, "clv": -0.03})
    assert dp.stop_status()["stop"]
    a = type("A", (), dict(match_id="m1", decision="PLAY", market="1X2", selection="HOME", price=2.0, bookmaker="x", stake=1.0, decided_by="t", note=""))()
    with pytest.raises(SystemExit):
        dp.cmd_record(a)
    a.decision, a.selection, a.price = "PASS", "", None
    dp.cmd_record(a)  # PASS still recordable
    dp.cmd_report()
    assert "DURDURULDU" in (tmp_path / "decisions/REPORT.md").read_text()


def test_stop_rule_not_triggered_early_or_when_positive(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    for i in range(49):
        dp.append_jsonl(tmp_path / "decisions/settlements.jsonl", {"decision_id": str(i), "decision": "PLAY", "clv": -0.05})
    assert not dp.stop_status()["stop"]
    for i in range(30):
        dp.append_jsonl(tmp_path / "decisions/settlements.jsonl", {"decision_id": f"p{i}", "decision": "PLAY", "clv": 0.20})
    assert not dp.stop_status()["stop"]


def test_scan_health_flags_broken_source():
    mk = lambda ok: {"context": {"data_present": {"odds": True, "opening_odds": True, "absences": ok, "xg": True, "elo": True, "weather": True}}}
    h = dp.scan_health("d", [1, 2, 3, 4], [mk(False), mk(False), mk(False), mk(True)])
    assert any("sakatlık" in w for w in h["warnings"]) and len(h["warnings"]) == 1
    assert not dp.scan_health("d", [1, 2], [mk(True), mk(True)])["warnings"]


def _rec_args(**k):
    return type("A", (), {**dict(match_id="m1", decision="PLAY", market="1X2", selection="HOME", price=2.0,
                                 bookmaker="x", stake=1.0, decided_by="t", note=""), **k})()


def _one_fixture(tmp_path, monkeypatch, day="2026-11-11"):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    d = tmp_path / "daily" / day; d.mkdir(parents=True)
    (d / "fixtures.json").write_text(json.dumps([{"match_id": "m1", "home": "A", "away": "B", "kickoff": KICK.isoformat()}]))


@pytest.mark.parametrize("kw", [dict(market="TOTAL", selection="HOME"), dict(selection="OVER_2.5"), dict(market="FOO", selection="BAR"),
                                dict(selection=""), dict(price=0.9), dict(price=1.0), dict(decision="WATCH", selection="")])
def test_record_refuses_ungradable_or_invalid(tmp_path, monkeypatch, kw):
    _one_fixture(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        dp.cmd_record(_rec_args(**kw))
    assert not (tmp_path / "decisions/decisions.jsonl").exists()


def test_record_accepts_valid_markets_and_refuses_duplicate_id(tmp_path, monkeypatch):
    _one_fixture(tmp_path, monkeypatch)
    dp.cmd_record(_rec_args(market="TOTAL", selection="OVER_2.5"))
    dp.cmd_record(_rec_args(market="DNB", selection="HOME_DNB"))
    dp.cmd_record(_rec_args(market="moneyline", selection="draw"))
    dp.cmd_record(_rec_args(decision="PASS", selection="", price=None))
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(dp, "datetime", type("D", (datetime,), {"now": classmethod(lambda c, tz=None: now), "fromisoformat": datetime.fromisoformat}))
    dp.cmd_record(_rec_args(selection="AWAY"))
    with pytest.raises(SystemExit):
        dp.cmd_record(_rec_args(selection="AWAY"))  # same match/stage/selection in the same second


def test_settle_survives_one_ungradable_old_record(tmp_path, monkeypatch):
    _one_fixture(tmp_path, monkeypatch)
    for i, (m, s) in enumerate([("FOO", "BAR"), ("1X2", "HOME")]):  # legacy bad record first
        dp.append_jsonl(tmp_path / "decisions/decisions.jsonl", {"decision_id": f"d{i}", "match_id": "m1", "decision": "PLAY",
                        "market": m, "selection": s, "price": 2.0, "stake": 1.0})
    monkeypatch.setattr(dp, "FlashscoreClient", lambda: FakeFS("finished", (2, 1)))
    monkeypatch.setattr(dp.time, "sleep", lambda s: None)
    dp.cmd_settle("2026-11-11")
    s = {x["decision_id"]: x for x in map(json.loads, (tmp_path / "decisions/settlements.jsonl").read_text().splitlines())}
    assert s["d0"]["result"] == "UNGRADABLE" and s["d0"]["pnl_units"] == 0 and s["d0"]["clv"] is None
    assert s["d1"]["result"] == "WIN"


def test_pending_settle_days(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    for day in ("2026-11-10", "2026-11-12", "2026-11-17", "2026-10-01"):
        d = tmp_path / "daily" / day; d.mkdir(parents=True); (d / "fixtures.json").write_text("[]")
    mk = lambda i, day: dp.append_jsonl(tmp_path / "decisions/decisions.jsonl", {"decision_id": i, "kickoff": f"{day}T15:00:00Z", "match_id": "m"})
    mk("a", "2026-11-10"); mk("b", "2026-11-12"); mk("c", "2026-11-17"); mk("old", "2026-10-01")
    dp.append_jsonl(tmp_path / "decisions/settlements.jsonl", {"decision_id": "b"})
    from datetime import date
    assert dp.pending_settle_days(date(2026, 11, 17)) == ["2026-11-10"]  # b settled, c is today, old is too old


def test_scan_health_flags_short_source_list():
    assert any("şüpheli" in w for w in dp.scan_health("d", [], [], source_total=0)["warnings"])
    assert not dp.scan_health("d", [], [], source_total=400)["warnings"]
    assert dp.scan_health("d", [], [])["source_matches_total"] is None


def test_clv_same_book_is_zero_for_no_skill_and_flags_missing_book():
    from market_evidence import clv_same_book, closing_odds_by_book
    q = [{"market": "1X2", "selection": s, "decimal_odds": o, "bookmaker": b, "phase": "CURRENT"}
         for b, odds in (("Bet365", (2.10, 3.40, 3.60)), ("Other", (2.20, 3.30, 3.50))) for s, o in zip(("HOME", "DRAW", "AWAY"), odds)]
    by = closing_odds_by_book(q, "1X2", "HOME")
    assert by == {"bet365": 2.10, "other": 2.20}
    r = clv_same_book(2.10, "bet365", by)          # took the closing price at the same book: no timing skill -> 0, not -vig
    assert r["clv"] == 0 and r["clv_basis"] == "SAME_BOOK" and r["clv_vs_best_close"] < 0
    assert clv_same_book(2.30, "Bet365", by)["clv"] == pytest.approx(0.0952, abs=1e-4)
    miss = clv_same_book(2.30, "nobody", by)
    assert miss["clv"] is None and miss["clv_basis"] == "BOOK_NOT_IN_CLOSING_QUOTES"
    assert clv_same_book(2.3, "x", {})["clv_basis"] == "NO_CLOSING_QUOTES"
    t = [{"market": "total", "selection": "OVER_2.5", "decimal_odds": 1.9, "bookmaker": "A", "phase": "CURRENT"},
         {"market": "total", "selection": "UNDER_2.5", "decimal_odds": 1.95, "bookmaker": "A", "phase": "CURRENT"}]
    assert closing_odds_by_book(t, "TOTAL", "OVER_2.5") == {"a": 1.9}


def _evidence(tmp_path, mid="m1", day="2026-11-11", home=2.30, over=1.95):
    d = tmp_path / "daily" / day
    (d / "packets").mkdir(parents=True, exist_ok=True); (d / "xi").mkdir(parents=True, exist_ok=True)
    bp = lambda o, b: {"odds": o, "bookmaker": b}
    (d / "packets" / f"{mid}.json").write_text(json.dumps({"market": {"summary": {
        "1x2": {"best_price": {"HOME": bp(2.25, "Coral"), "DRAW": bp(3.4, "bet365"), "AWAY": bp(3.6, "Skybet")}},
        "totals": {"2.5": {"best_price": {"OVER": bp(over, "Unibetuk"), "UNDER": bp(1.9, "10bet")}}}}}}))
    (d / "xi" / f"{mid}.json").write_text(json.dumps({"market": {"1x2": {"best_price": {"HOME": bp(home, "Midnite")}}}}))


def test_record_infers_bookmaker_from_price(tmp_path, monkeypatch):
    _one_fixture(tmp_path, monkeypatch)
    _evidence(tmp_path)
    got = lambda: [json.loads(l) for l in (tmp_path / "decisions/decisions.jsonl").read_text().splitlines()][-1]
    dp.cmd_record(_rec_args(selection="HOME", price=2.30, bookmaker=None))    # matches the XI-time best price
    assert got()["bookmaker"] == "Midnite" and got()["bookmaker_source"] == "INFERRED_FROM_EVIDENCE_BEST_PRICE"
    dp.cmd_record(_rec_args(selection="DRAW", price=3.4, bookmaker=None))     # morning packet
    assert got()["bookmaker"] == "bet365"
    dp.cmd_record(_rec_args(market="TOTAL", selection="OVER_2.5", price=1.95, bookmaker=None))
    assert got()["bookmaker"] == "Unibetuk"
    dp.cmd_record(_rec_args(selection="AWAY", price=3.5, bookmaker=None))     # price not in any file -> no guess
    assert got()["bookmaker"] is None and got()["bookmaker_source"] == "UNKNOWN_NO_CLV"
    dp.cmd_record(_rec_args(market="TOTAL", selection="UNDER_2.5", price=1.9, bookmaker="Given"))
    assert got()["bookmaker"] == "Given" and got()["bookmaker_source"] == "GIVEN"
