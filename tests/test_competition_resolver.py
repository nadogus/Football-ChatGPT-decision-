from datetime import datetime,timezone
from competition_resolver import FlashscoreCompetitionResolver,pinnacle_catalog_match,text_similarity,flashscore_country_from_link

def test_catalog_match_generalizes_across_major_leagues():
    rows=[{"id":1001,"name":"Spain - La Liga","group":"Spain","sequence":1},{"id":1002,"name":"Italy - Serie A","group":"Italy","sequence":1},{"id":1003,"name":"Germany - Bundesliga","group":"Germany","sequence":1},{"id":1004,"name":"France - Ligue 1","group":"France","sequence":1},{"id":1005,"name":"Netherlands - Eredivisie","group":"Netherlands","sequence":1}]
    cases=[({"name":"LaLiga","display_name":"SPAIN: LaLiga","country":"Spain"},1001),({"name":"Serie A","display_name":"ITALY: Serie A","country":"Italy"},1002),({"name":"Bundesliga","display_name":"GERMANY: Bundesliga","country":"Germany"},1003),({"name":"Ligue 1","display_name":"FRANCE: Ligue 1","country":"France"},1004),({"name":"Eredivisie","display_name":"NETHERLANDS: Eredivisie","country":"Netherlands"},1005)]
    for profile,expected in cases:
        out=pinnacle_catalog_match(profile,rows);assert out["resolved"] is True;assert out["league_id"]==expected

def test_laliga_catalog_match_without_country_metadata():
    rows=[{"id":2464,"name":"Spain - La Liga","group":"Spain"},{"id":9999,"name":"Spain - La Liga Women","group":"Spain"}]
    out=pinnacle_catalog_match({"name":"LaLiga","display_name":"LaLiga","country":None},rows)
    assert out["resolved"] is True
    assert out["league_id"]==2464

def test_catalog_match_penalizes_women_variant():
    profile={"name":"Serie A","display_name":"ITALY: Serie A","country":"Italy"};rows=[{"id":1,"name":"Italy - Serie A Women","group":"Italy","sequence":1},{"id":2,"name":"Italy - Serie A","group":"Italy","sequence":2}];out=pinnacle_catalog_match(profile,rows);assert out["resolved"] is True;assert out["league_id"]==2

def test_catalog_match_fails_closed_on_ambiguity():
    profile={"name":"Premier Division","display_name":"IRELAND: Premier Division","country":"Ireland"};rows=[{"id":1,"name":"Ireland - Premier Division","group":"Ireland"},{"id":2,"name":"Ireland - Premier Division A","group":"Ireland"}];out=pinnacle_catalog_match(profile,rows,margin=.20);assert out["resolved"] is False;assert out["reason"]=="AMBIGUOUS_LEAGUE"

def test_flashscore_profile_uses_metadata_not_hardcoded_country(monkeypatch):
    resolver=FlashscoreCompetitionResolver("http://unused");monkeypatch.setattr(resolver,"team_id",lambda team:"TEAM1")
    class R:
        ok=True;data={"competitions":[{"competition":{"id":"abc","stage_id":"stage","name":"Eredivisie","display_name":"NETHERLANDS: Eredivisie","category":"Netherlands","link":"https://www.flashscore.com/football/netherlands/eredivisie/"},"matches":[{"start_time":"2026-10-20T18:00:00Z"}]}]}
    monkeypatch.setattr(resolver.client,"team_results",lambda team_id,page=1:R());out=resolver.profile("Ajax","Eredivisie",datetime(2026,10,31,tzinfo=timezone.utc));assert out is not None;assert out["country"]=="Netherlands";assert out["name"]=="Eredivisie";assert out["link"].endswith("/eredivisie/")

def test_text_similarity_handles_accents_and_formatting():assert text_similarity("Türkiye Süper Lig","Turkey Super Lig")>.45


def test_flashscore_country_from_verified_tournament_link():
    assert flashscore_country_from_link("https://www.flashscore.com/football/spain/laliga/")=="Spain"
    assert flashscore_country_from_link("https://www.flashscore.com/football/turkey/super-lig/")=="Turkey"
