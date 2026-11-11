from fotmob_source import FotMobClient, absences, lineup

DETAILS = {"content": {"lineup": {"lineupType": "standard", "homeTeam": {
    "name": "Napoli", "formation": "3-4-2-1",
    "starters": [{"id": i, "name": f"N{i}"} for i in range(11)],
    "unavailable": [{"name": "Benoît Badiashile", "unavailability": {"type": "injury", "expectedReturn": "Early December 2026"}},
                    {"name": "Luca Marianucci", "unavailability": {"type": "suspension", "expectedReturn": "Early November 2026"}}]},
    "awayTeam": {"name": "Lazio", "starters": [{"id": i, "name": f"L{i}"} for i in range(11)], "unavailable": []}}}}


def test_absences_keep_reason_and_return():
    a = absences(DETAILS)
    assert [r["reason"] for r in a["home"]] == ["injury", "suspension"]
    assert a["home"][0]["likelihood"] == "Early December 2026"
    assert a["away"] == []          # FotMob block present: genuinely empty list
    assert absences({}) is None      # block missing: unknown


def test_lineup_never_official_when_predicted_or_unavailable():
    assert lineup(DETAILS)["official"]
    for t in ("unavailable", "predicted"):
        d = {"content": {"lineup": {**DETAILS["content"]["lineup"], "lineupType": t}}}
        assert not lineup(d)["official"]


def test_resolve_by_names_and_time():
    payload = {"leagues": [{"name": "Serie A", "matches": [
        {"id": 1, "home": {"name": "Napoli"}, "away": {"name": "Lazio"}, "status": {"utcTime": "2026-11-08T11:30:00Z"}},
        {"id": 2, "home": {"name": "Roma"}, "away": {"name": "Inter"}, "status": {"utcTime": "2026-11-08T19:45:00Z"}}]}]}
    c = FotMobClient(getter=lambda path: payload)
    r = c.resolve({"home": "Napoli", "away": "Lazio", "kickoff": "2026-11-08T11:30:00+00:00"})
    assert r["resolved"] and r["id"] == "1"
