from fixture_resolver import fixture_score, best_fixture, _walk_events


def test_exact_fixture_resolves():
    match={"home":"Liverpool","away":"Arsenal","kickoff":"2026-11-01T16:30:00+00:00"}
    candidates=[
        {"id":"123","home":"Liverpool FC","away":"Arsenal","kickoff":"2026-11-01T16:30:00Z"},
        {"id":"999","home":"Liverpool","away":"Chelsea","kickoff":"2026-11-01T16:30:00Z"},
    ]
    r=best_fixture(match,candidates)
    assert r["resolved"] is True
    assert r["id"]=="123"
    assert r["score"] >= 0.86


def test_flashscore_prefers_precise_start_time_over_date():
    payload=[{
        "id":"abc",
        "home":{"name":"Liverpool"},
        "away":{"name":"Arsenal"},
        "date":"2026-11-01",
        "start_time":"2026-11-01T16:30:00Z",
    }]
    rows=_walk_events(payload)
    assert rows[0]["kickoff"]=="2026-11-01T16:30:00Z"


def test_ambiguous_fixture_fails_closed():
    match={"home":"United","away":"City","kickoff":"2026-11-01T16:30:00+00:00"}
    candidates=[
        {"id":"1","home":"United","away":"City","kickoff":"2026-11-01T16:30:00Z"},
        {"id":"2","home":"United","away":"City","kickoff":"2026-11-01T16:31:00Z"},
    ]
    r=best_fixture(match,candidates)
    assert r["resolved"] is False
    assert r["reason"]=="AMBIGUOUS_MATCH"


def test_wrong_kickoff_rejected():
    match={"home":"Liverpool","away":"Arsenal","kickoff":"2026-11-01T16:30:00+00:00"}
    candidates=[
        {"id":"123","home":"Liverpool","away":"Arsenal","kickoff":"2026-11-02T16:30:00Z"},
    ]
    r=best_fixture(match,candidates)
    assert r["resolved"] is False
