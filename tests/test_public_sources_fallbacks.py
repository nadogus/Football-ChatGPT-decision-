from datetime import datetime, timezone
from public_sources import ClubEloClient, UnderstatClient

def test_clubelo_web_history_parser_reads_vega_rows():
    html='''<script>vegaJson = {"data":{"values":[{"Date":"2026-10-30","Elo":1888.5},{"Date":"2026-10-31","Elo":1891.2}]}};</script>'''
    rows=ClubEloClient._parse_web_history(html)
    assert rows[-1]["From"]=="2026-10-31"
    assert rows[-1]["Elo"]=="1891.2"

def test_clubelo_web_history_parser_fails_closed_unknown_shape():
    assert ClubEloClient._parse_web_history("<html>no data</html>")==[]

def test_understat_ajax_team_summary_current_shape(monkeypatch):
    client=UnderstatClient()
    payload={"dates":[
        {"isResult":True,"h":{"title":"Liverpool"},"a":{"title":"Arsenal"},"xG":{"h":"2.10","a":"1.20"}},
        {"isResult":True,"h":{"title":"Chelsea"},"a":{"title":"Liverpool"},"xG":{"h":"1.30","a":"1.70"}},
    ]}
    monkeypatch.setattr(client,"_ajax",lambda path:payload)
    out=client.team_xg_summary("Liverpool",2026,last_n=10)
    assert out is not None
    assert round(out["xg_for"],2)==1.90
    assert round(out["xg_against"],2)==1.25
    assert out["source"]=="understat_ajax"

def test_understat_computed_elo_from_league_dates(monkeypatch):
    client=UnderstatClient()
    payload={"dates":[
        {"isResult":True,"datetime":"2026-09-01T15:00:00Z","h":{"title":"Liverpool"},"a":{"title":"Arsenal"},"goals":{"h":"2","a":"0"}},
        {"isResult":True,"datetime":"2026-09-08T15:00:00Z","h":{"title":"Arsenal"},"a":{"title":"Chelsea"},"goals":{"h":"1","a":"0"}},
    ]}
    monkeypatch.setattr(client,"league_data",lambda league,season:payload)
    ratings=client.computed_elo("EPL",2026,datetime(2026,11,1,tzinfo=timezone.utc))
    assert "Liverpool" in ratings and "Arsenal" in ratings
    assert ratings["Liverpool"]>1500
