import json
from datetime import datetime, timedelta, timezone

import live_watch as lw


def details(minute="58'", score=(0, 0), xg=("1.62", "0.31"), xgot=("1.10", "0.20"), red=(0, 0), started=True, finished=False,
            drop_xg=False):
    stats = [
        {"title": "Top stats", "key": "top_stats", "stats": [
            {"title": "Ball possession", "key": "BallPossesion", "stats": [61, 39]},
            {"title": "Total shots", "key": "total_shots", "stats": [12, 4]},
            {"title": "Shots on target", "key": "ShotsOnTarget", "stats": [5, 1]},
            {"title": "Big chances", "key": "big_chance", "stats": [3, 0]},
        ]},
        {"title": "Expected goals (xG)", "key": "expected_goals", "stats": [
            {"title": "xG on target (xGOT)", "key": "expected_goals_on_target", "stats": list(xgot)},
        ]},
        {"title": "Attack", "key": "attack", "stats": [
            {"title": "Touches in opposition box", "key": "touches_opp_box", "stats": [24, 7]},
        ]},
        {"title": "Discipline", "key": "discipline", "stats": [
            {"title": "Red cards", "key": "red_cards", "stats": list(red)},
        ]},
    ]
    if not drop_xg:
        stats[0]["stats"].append({"title": "Expected goals (xG)", "key": "expected_goals", "stats": list(xg)})
    return {
        "header": {"teams": [{"name": "Arsenal", "score": score[0]}, {"name": "Chelsea", "score": score[1]}],
                   "status": {"started": started, "finished": finished, "liveTime": {"short": minute}}},
        "content": {"stats": {"Periods": {"All": {"stats": stats}}}},
    }


NOW = datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)


def test_extract_stats_and_header():
    s = lw.snapshot(details(), NOW)
    assert s["minute"] == 58 and s["score"] == [0, 0] and s["home"] == "Arsenal"
    assert s["stats"]["xg"] == [1.62, 0.31]
    assert s["stats"]["xgot"] == [1.10, 0.20]
    assert s["stats"]["box_touches"] == [24, 7]
    assert s["stats"]["possession"] == [61, 39]
    assert "xg" not in s["missing"]


def test_missing_stat_is_not_invented():
    s = lw.snapshot(details(drop_xg=True), NOW)
    assert s["stats"]["xg"] is None and "xg" in s["missing"]
    assert lw.triggers(s, []) == []


def test_pressure_and_open_game_triggers():
    keys = {k for k, _ in lw.triggers(lw.snapshot(details(), NOW), [])}
    assert "baski_0" in keys and "acik_mac" not in keys
    s = lw.snapshot(details(xg=("1.3", "1.1"), score=(1, 0)), NOW)
    assert {k for k, _ in lw.triggers(s, [])} == {"acik_mac"}
    # baskın taraf zaten öndeyse baskı uyarısı yok
    assert not lw.triggers(lw.snapshot(details(score=(1, 0)), NOW), [])


def test_no_triggers_outside_window_or_finished():
    assert lw.triggers(lw.snapshot(details(minute="9'"), NOW), []) == []
    assert lw.triggers(lw.snapshot(details(minute="88'"), NOW), []) == []
    assert lw.triggers(lw.snapshot(details(finished=True), NOW), []) == []


def test_surge_and_red_card():
    past = lw.snapshot(details(minute="42'", xg=("0.70", "0.30")), NOW)
    now = lw.snapshot(details(minute="58'", xg=("1.50", "0.31"), red=(0, 1)), NOW)
    keys = {k for k, _ in lw.triggers(now, [past])}
    assert "atak_0_3" in keys and "kirmizi_1_1" in keys


class FakeClient:
    def __init__(self, d):
        self.d = d

    def resolve(self, fx):
        return {"resolved": True, "id": "4500001"}

    def details(self, fid):
        return self.d


def test_run_writes_snapshots_and_alerts_once(tmp_path):
    day = tmp_path / "daily" / "2026-11-21"
    day.mkdir(parents=True)
    ko = (NOW - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (day / "fixtures.json").write_text(json.dumps([{"match_id": "abc", "home": "Arsenal", "away": "Chelsea",
                                                    "kickoff": ko, "competition": "Premier League"}]))
    sent = []
    rep = lw.run(NOW, FakeClient(details()), root=tmp_path, send=sent.append)
    assert rep == {"watched": 1, "alerts": 1}
    assert "canlı bak 4500001" in sent[0]
    rep = lw.run(NOW + timedelta(minutes=5), FakeClient(details(minute="63'")), root=tmp_path, send=sent.append)
    assert rep["alerts"] == 0 and len(sent) == 1
    lines = (day / "live" / "4500001.jsonl").read_text().splitlines()
    assert len(lines) == 2
    idx = json.loads((day / "live" / "index.json").read_text())
    assert idx["4500001"]["flashscore_id"] == "abc"


def test_fixture_window(tmp_path):
    day = tmp_path / "daily" / "2026-11-21"
    day.mkdir(parents=True)
    mk = lambda m: {"match_id": str(m), "home": "A", "away": "B",
                    "kickoff": (NOW - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (day / "fixtures.json").write_text(json.dumps([mk(-30), mk(10), mk(200)]))
    assert [f["match_id"] for f in lw.live_fixtures(NOW, tmp_path)] == ["10"]
