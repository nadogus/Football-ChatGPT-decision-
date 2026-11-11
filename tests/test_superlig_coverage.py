from datetime import datetime,timezone
from data_adapters import normalize_decimal_quotes
from public_sources import FlashscoreModelClient

def test_flashscore_opening_odds_nested_shape():
    payload={"markets":[
        {"bet_type":"HOME_DRAW_AWAY","bet_scope":"FULL_TIME","bookmaker":{"name":"bet365.us"},"selections":[
            {"selection":"HOME","value":"1.49","opening_value":"1.27"},
            {"selection":"DRAW","value":"4.33","opening_value":"5.25"},
            {"selection":"AWAY","value":"5.0","opening_value":"8.0"}]},
        {"bet_type":"OVER_UNDER","bet_scope":"FULL_TIME","bookmaker":{"name":"bet365.us"},"selections":[
            {"selection":"OVER","handicap":"{'__typename': 'EventOddsItemHandicap', 'value': '2.5', 'type': 'UNKNOWN'}","value":"1.90","opening_value":"1.85"},
            {"selection":"UNDER","handicap":{"value":"2.5"},"value":"1.95","opening_value":"2.00"}]}
    ]}
    rows=normalize_decimal_quotes(payload,"flashscore",prefer_opening=True)
    by={(r["market"],r["selection"]):r for r in rows}
    assert by[("moneyline","HOME")]["decimal_odds"]==1.27
    assert by[("moneyline","DRAW")]["decimal_odds"]==5.25
    assert by[("moneyline","AWAY")]["decimal_odds"]==8.0
    assert by[("total","OVER_2.5")]["decimal_odds"]==1.85
    assert by[("total","UNDER_2.5")]["decimal_odds"]==2.0
    assert all(r["phase"]=="OPENING" for r in rows)

def test_flashscore_computed_elo_excludes_target_match(monkeypatch):
    c=FlashscoreModelClient("http://unused")
    monkeypatch.setattr(c,"competition_ref",lambda *a:"https://www.flashscore.com/football/turkey/super-lig/")
    class R:
        ok=True
        data={"matches":[
            {"id":"pre","start_time":"2026-10-30T16:00:00Z","status":"finished","home":{"name":"Fenerbahce"},"away":{"name":"Goztepe"},"home_score":2,"away_score":0},
            {"id":"target","start_time":"2026-10-31T16:00:00Z","status":"finished","home":{"name":"Fenerbahce"},"away":{"name":"Goztepe"},"home_score":0,"away_score":5},
        ],"pagination":{"total_pages":1}}
    monkeypatch.setattr(c.client,"tournament_results",lambda ref,page=1:R())
    ratings=c.computed_elo("Fenerbahce","Super Lig",datetime(2026,10,31,16,0,tzinfo=timezone.utc))
    assert ratings["Fenerbahce"]>1500
    assert ratings["Goztepe"]<1500
