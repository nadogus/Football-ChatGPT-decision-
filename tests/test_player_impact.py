from datetime import datetime, timezone

import player_impact as pi

BEFORE = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)


def stat(v):
    return {"stat": {"value": v, "type": "double"}}


def player(pid, name, team, minutes, xg=0.0, xa=0.0, shots=0, kp=0, gk=False, gp=None, saves=None):
    top = {"Minutes played": stat(minutes), "Expected goals (xG)": stat(xg), "Expected assists (xA)": stat(xa),
           "Total shots": stat(shots), "Chances created": stat(kp)}
    if gp is not None:
        top["Goals prevented"] = stat(gp)
        top["Saves"] = stat(saves or 0)
    return str(pid), {"name": name, "teamId": team, "isGoalkeeper": gk, "stats": [{"key": "top_stats", "stats": top}]}


def match(team, rows):
    return {"content": {"playerStats": dict(rows)}}


def make_get(n_matches=10, drop_stats_from=None):
    fixtures = [{"id": 100 + i, "status": {"finished": True, "utcTime": f"2026-11-{15 - i:02d}T15:00:00Z"}} for i in range(n_matches)]
    fixtures.append({"id": 999, "status": {"finished": False, "utcTime": "2026-11-30T15:00:00Z"}})  # future: ignored
    def get(path):
        if path.startswith("/teams?id=7"):
            return {"fixtures": {"allFixtures": {"fixtures": fixtures}}}
        if path.startswith("/matchDetails?matchId="):
            mid = int(path.split("=")[1])
            i = mid - 100
            if drop_stats_from is not None and i >= drop_stats_from:
                return {"content": {}}
            return match(7, [player(1, "Star Striker", 7, 90, xg=0.6, xa=0.1, shots=4, kp=1),
                             player(2, "Bench Guy", 7, 20 if i < 5 else 0, xg=0.05, shots=1),
                             player(3, "Keeper One", 7, 90, gk=True, gp=0.3, saves=3),
                             player(9, "Other Team", 8, 90, xg=5)])
        raise AssertionError(path)
    return get


def test_parse_player_stats_and_missing_block():
    s = pi.parse_player_stats(match(7, [player(1, "A B", 7, 90, xg=0.4)]))
    assert s["1"]["minutes"] == 90 and s["1"]["xg"] == 0.4 and "xa" in s["1"]
    assert pi.parse_player_stats({}) == {} and pi.parse_player_stats({"content": {"playerStats": None}}) == {}


def test_recent_match_ids_only_finished_before_kickoff_newest_first():
    fx = [{"id": 1, "status": {"finished": True, "utcTime": "2026-11-01T10:00:00Z"}},
          {"id": 2, "status": {"finished": True, "utcTime": "2026-11-08T10:00:00Z"}},
          {"id": 3, "status": {"finished": False, "utcTime": "2026-11-29T10:00:00Z"}}]
    assert pi.recent_match_ids(fx, BEFORE, 10) == [2, 1]
    assert pi.recent_match_ids(fx, BEFORE, 1) == [2]


def test_profile_windows_per90_and_share():
    hist, why = pi.load_history(make_get(), 7, BEFORE, 10)
    assert why is None and len(hist.matches) == 10
    p = pi.player_profile(hist, "Star Striker")
    assert p["windows"]["5"]["minutes"] == 450 and p["windows"]["10"]["appearances"] == 10
    assert p["windows"]["10"]["per90"]["xg"] == 0.6
    assert 0.8 < p["windows"]["10"]["attack_share"] < 0.95  # (0.7) / (0.7 + 0.05)
    bench = pi.player_profile(hist, "Bench Guy")
    assert bench["windows"]["5"]["appearances"] == 5 and bench["windows"]["10"]["appearances"] == 5
    assert pi.player_profile(hist, "Never Seen") is None


def test_replacement_gap_and_goalkeeper():
    hist, _ = pi.load_history(make_get(), 7, BEFORE, 10)
    ch = {"count": 1, "out": ["Star Striker"], "in": ["Bench Guy"], "goalkeeper_changed": True,
          "goalkeeper": "Keeper One", "previous_goalkeeper": "Unknown Keeper"}
    imp = pi.side_impact(hist, ch, [{"name": "Bench Guy", "id": "espn:2"}], [{"name": "Star Striker", "id": "espn:1"}])
    assert imp["status"] == "OK" and imp["replacement_gap"][0]["delta_per90"]["xg"] < 0
    assert imp["goalkeeper"]["now"]["games"] == 10 and imp["goalkeeper"]["previous"] is None
    txt = "\n".join(pi.render_side("Team", imp))
    assert "Star Striker" in txt and "küçük örneklem" in txt and "veri yok" in txt


def test_unknown_player_is_reported_not_invented():
    hist, _ = pi.load_history(make_get(), 7, BEFORE, 10)
    ch = {"count": 1, "out": ["Nobody Known"], "in": ["Star Striker"], "goalkeeper_changed": False}
    imp = pi.side_impact(hist, ch, [{"name": "Star Striker"}], [{"name": "Nobody Known"}])
    assert imp["out"][0]["windows"] is None and imp["replacement_gap"] == []


def test_build_fails_closed():
    xi = {s: {"starters": []} for s in ("home", "away")}
    details = {"general": {"homeTeam": {"id": 7}, "awayTeam": {"id": 8}}}
    ch = {"home": {"count": 1, "out": ["Star Striker"], "in": ["Bench Guy"], "goalkeeper_changed": False}, "away": None}
    out, gaps = pi.build(make_get(drop_stats_from=0), details, BEFORE, xi, ch, {})
    assert out["home"]["status"] == "VERİ YOK" and any("PLAYER_STATS_UNAVAILABLE" in g for g in gaps)
    assert out["away"]["status"] == "ONCEKI_KADRO_YOK"

    def boom(path):
        raise RuntimeError("403")
    out, gaps = pi.build(boom, details, BEFORE, xi, ch, {})
    assert out["home"]["status"] == "VERİ YOK" and gaps
    out, gaps = pi.build(boom, None, BEFORE, xi, ch, {})
    assert out["home"]["status"] == "VERİ YOK" and any("NO_TEAM_ID" in g for g in gaps)


def test_partial_history_is_flagged():
    xi = {s: {"starters": [{"name": "Star Striker", "id": "x"}]} for s in ("home", "away")}
    details = {"general": {"homeTeam": {"id": 7}, "awayTeam": {"id": 8}}}
    ch = {"home": {"count": 1, "out": ["Star Striker"], "in": ["Bench Guy"], "goalkeeper_changed": False}, "away": None}
    out, gaps = pi.build(make_get(drop_stats_from=6), details, BEFORE, xi, ch, {})
    assert out["home"]["status"] == "OK" and any("PARTIAL_HISTORY:home:6/10" in g for g in gaps)
