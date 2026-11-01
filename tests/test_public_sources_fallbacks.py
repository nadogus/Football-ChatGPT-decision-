from datetime import datetime, timezone
from public_sources import ClubEloClient, UnderstatClient, SofaScoreClient

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

def test_sofascore_computed_elo_from_finished_events(monkeypatch):
    client=SofaScoreClient()
    monkeypatch.setattr(client,"season_id_for_date",lambda tournament_id,as_of:999)
    events=[
        {
            "startTimestamp":1793500000,
            "status":{"type":"finished"},
            "homeTeam":{"name":"Liverpool"},
            "awayTeam":{"name":"Arsenal"},
            "homeScore":{"current":2},
            "awayScore":{"current":0},
        },
        {
            "startTimestamp":1793600000,
            "status":{"type":"finished"},
            "homeTeam":{"name":"Arsenal"},
            "awayTeam":{"name":"Chelsea"},
            "homeScore":{"current":1},
            "awayScore":{"current":0},
        },
    ]
    monkeypatch.setattr(client,"season_events",lambda tournament_id,season_id:events)
    ratings=client.computed_elo(17,datetime(2026,11,2,tzinfo=timezone.utc))
    assert "Liverpool" in ratings
    assert "Arsenal" in ratings
    assert ratings["Liverpool"]>1500
