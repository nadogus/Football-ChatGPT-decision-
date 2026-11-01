from source_pipeline import parse_flashscore_xi, verify_official_xi

def row(i):
    return {"player":{"id":str(i),"name":f"P{i}"}}

def test_parse_combined_flashscore_starting_lineups():
    payload={
        "home":{"formation":"1-4-2-3-1","groups":[{"name":"Starting Lineups","players":[row(i) for i in range(1,23)]}]},
        "away":{"formation":"1-4-3-3","groups":[{"name":"Substitutes","players":[row(i) for i in range(23,31)]}]},
    }
    parsed=parse_flashscore_xi(payload)
    assert parsed["home_starters"]==[str(i) for i in range(1,12)]
    assert parsed["away_starters"]==[str(i) for i in range(12,23)]
    assert parsed["formation_home"]=="1-4-2-3-1"
    assert parsed["formation_away"]=="1-4-3-3"
    assert parsed["parse_mode"]=="COMBINED_22_HOME_THEN_AWAY"
    assert verify_official_xi(payload,[["validator"]*11])["starter_count"]==22

def test_parse_separate_side_groups():
    payload={
        "home":{"groups":[{"name":"Starting Lineups","players":[row(i) for i in range(1,12)]}]},
        "away":{"groups":[{"name":"Starting Lineups","players":[row(i) for i in range(12,23)]}]},
    }
    parsed=parse_flashscore_xi(payload)
    assert len(parsed["home_starters"])==11
    assert len(parsed["away_starters"])==11
    assert parsed["parse_mode"]=="SEPARATE_SIDE_GROUPS"
