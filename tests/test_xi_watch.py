import json
from datetime import datetime, timedelta, timezone

import xi_watch as xw
from data_adapters import AdapterResult


def lineup(n_home=11, n_away=11, group="Starting Lineups"):
    mk = lambda side, n: {"formation": "4-3-3", "groups": [
        {"name": group, "players": [{"player": {"id": f"{side}{i}", "name": f"Player{side}{i} A."},
                                     "is_goalkeeper": i == 0, "is_captain": i == 1, "shirt_number": i} for i in range(n)]},
        {"name": "Substitutes", "players": []}]}
    return {"home": mk("h", n_home), "away": mk("a", n_away)}


def test_official_xi_is_strict():
    assert xw.official_xi(lineup())["official"]
    assert not xw.official_xi(lineup(10, 11))["official"]
    assert not xw.official_xi(lineup(group="Predicted lineups"))["official"]
    assert not xw.official_xi({})["official"]


def test_surname_and_cross_check():
    assert xw.surname("Salah M.") == xw.surname("Mohamed Salah") == "salah"
    assert xw.surname("van Dijk V.") == "van" or xw.surname("van Dijk V.") == "dijk"
    xi = xw.official_xi(lineup())
    names = [p["name"].split()[0] for s in ("home", "away") for p in xi[s]["starters"]]
    ok = xw.cross_check(xi, [f"Joe {n}" for n in names])
    assert ok["validated"] and ok["matched_share"] == 1.0
    assert not xw.cross_check(xi, ["a"] * 5)["validated"]


def espn_summary(n=11, published=True):
    mk = lambda side: {"homeAway": side, "formation": "4-3-3", "roster": [
        {"starter": published and i < n, "jersey": str(i), "athlete": {"id": f"{side}{i}", "displayName": f"Joe Player{side}{i}"},
         "position": {"abbreviation": "G" if i == 0 else "M"}} for i in range(18)]}
    return {"rosters": [mk("home"), mk("away")]}


def test_espn_xi():
    x = xw.espn_xi(espn_summary())
    assert x["official"] and x["home"]["starters"][0]["gk"] and x["home"]["formation"] == "4-3-3"
    assert not xw.espn_xi(espn_summary(published=False))["official"]
    assert not xw.espn_xi({})["official"]


def test_changes_detect_goalkeeper():
    now = [{"id": "1", "name": "A", "gk": True}, {"id": "2", "name": "B", "gk": False}]
    prev = [{"id": "9", "name": "Z", "gk": True}, {"id": "2", "name": "B", "gk": False}]
    c = xw.changes(now, prev)
    assert c["count"] == 1 and c["out"] == ["Z"] and c["goalkeeper_changed"]
    assert xw.changes(now, None) is None


class FakeFS:
    base = "http://fake"
    def __init__(self, official=True): self.official = official
    def lineups(self, mid): return AdapterResult("flashscore", True, lineup() if self.official else lineup(group="Predicted lineups"))
    def missing_players(self, mid): return AdapterResult("flashscore", True, {"home": [], "away": []})
    def odds(self, mid, geo=None): return AdapterResult("flashscore", True, {"markets": []})
    def team_results(self, tid, page=1): return AdapterResult("flashscore", False, {}, "NO")


def _setup(tmp_path, monkeypatch, minutes_to_kick, official=True):
    monkeypatch.setattr(xw, "ROOT", tmp_path)
    now = datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc)
    d = tmp_path / "daily" / "2026-11-22"
    d.mkdir(parents=True)
    fx = [{"match_id": "m1", "home": "Liverpool", "away": "Arsenal", "kickoff": (now + timedelta(minutes=minutes_to_kick)).isoformat(),
           "competition": "Premier League", "category": "England"}]
    (d / "fixtures.json").write_text(json.dumps(fx))
    w = xw.Watcher.__new__(xw.Watcher)
    w.fs = FakeFS(official)
    w.fotmob = type("F", (), {"resolve": lambda self, fx: {"resolved": False, "reason": "TEST"}})()
    w.leagues = [{"category": "England", "name": "Premier League", "espn": "eng.1"}]
    monkeypatch.setattr(xw, "resolve_espn", lambda fx, slug: {"resolved": True, "id": "e1"})
    summ = espn_summary(published=official)
    monkeypatch.setattr(xw, "ESPNLineupClient", lambda: type("E", (), {"summary": lambda self, slug, eid: AdapterResult("espn", True, summ)})())
    monkeypatch.setattr(xw, "espn_previous_xi", lambda slug, team, before: None)
    w.model = type("M", (), {"team_id": lambda self, t: None})()
    monkeypatch.setattr(xw, "Watcher", lambda: w)
    sent = []
    monkeypatch.setattr(xw, "notify", lambda text, title: sent.append(title) or ["test"])
    return now, d, sent


def test_window_confirm_notify_once(tmp_path, monkeypatch):
    now, d, sent = _setup(tmp_path, monkeypatch, 55)
    xw.run(now=now)
    st = json.loads((d / "xi_state.json").read_text())
    assert st["m1"]["status"] == "CONFIRMED" and sent == ["XI: Liverpool - Arsenal"]
    md = (d / "xi" / "m1.md").read_text()
    assert "resmi kadrolar" in md and "Kanıttır, karar değildir" in md
    assert (tmp_path / "ledger" / "post_xi_evidence.jsonl").exists()
    xw.run(now=now + timedelta(minutes=10))
    assert sent == ["XI: Liverpool - Arsenal"]  # not re-notified


def test_outside_window_and_predicted_not_confirmed(tmp_path, monkeypatch):
    now, d, sent = _setup(tmp_path, monkeypatch, 120)
    xw.run(now=now)
    assert not (d / "xi_state.json").exists() or json.loads((d / "xi_state.json").read_text()) == {}


def test_predicted_lineup_stays_pending(tmp_path, monkeypatch):
    now, d, sent = _setup(tmp_path, monkeypatch, 50, official=False)
    xw.run(now=now)
    st = json.loads((d / "xi_state.json").read_text())
    assert st["m1"]["status"] == "NOT_YET" and not sent


def test_past_match_force_is_validation_only(tmp_path, monkeypatch):
    now, d, sent = _setup(tmp_path, monkeypatch, -120)
    xw.run(now=now, day="2026-11-22", match_id="m1", force=True)
    rec = json.loads((d / "xi" / "m1.json").read_text())
    assert rec["event"] == "XI_VALIDATION_ONLY" and not sent
    assert not (tmp_path / "ledger" / "post_xi_evidence.jsonl").exists()
