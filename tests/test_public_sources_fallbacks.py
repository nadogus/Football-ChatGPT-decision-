import json
from public_sources import ClubEloClient

def test_clubelo_web_history_parser_reads_vega_rows():
    html='''<script>vegaJson = {"data":{"values":[{"Date":"2026-10-30","Elo":1888.5},{"Date":"2026-10-31","Elo":1891.2}]}};</script>'''
    rows=ClubEloClient._parse_web_history(html)
    assert rows[-1]["From"]=="2026-10-31"
    assert rows[-1]["Elo"]=="1891.2"

def test_clubelo_web_history_parser_fails_closed_unknown_shape():
    assert ClubEloClient._parse_web_history("<html>no data</html>")==[]
