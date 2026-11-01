"""Temporary live Flashscore shape diagnostic for competition resolver."""
from __future__ import annotations
import json
from data_adapters import FlashscoreClient

def slim(x, depth=0):
    if depth>4:
        return "<depth>"
    if isinstance(x, dict):
        out={}
        for k,v in list(x.items())[:20]:
            if str(k).lower() in {"cookie","authorization","token","apikey","api_key"}:
                out[k]="<redacted>"
            else:
                out[k]=slim(v,depth+1)
        return out
    if isinstance(x,list):
        return [slim(v,depth+1) for v in x[:3]]
    return x

def first_rows(data):
    if isinstance(data,list):
        return data
    if isinstance(data,dict):
        for key in ("results","data","items","teams"):
            rows=data.get(key)
            if isinstance(rows,list):
                return rows
    return []

def main():
    fs=FlashscoreClient()
    for team in ["Liverpool","Fenerbahce","Barcelona"]:
        s=fs.search(team,entity_type="team",sport="football",limit=5)
        print("SEARCH",team,json.dumps(slim({"ok":s.ok,"error":s.error,"data":s.data}),ensure_ascii=False))
        tid=None
        for row in first_rows(s.data) if s.ok else []:
            if isinstance(row,dict) and row.get("id"):
                tid=str(row["id"]);break
        if tid:
            r=fs.team_results(tid,page=1)
            print("RESULTS",team,tid,json.dumps(slim({"ok":r.ok,"error":r.error,"data":r.data}),ensure_ascii=False))

if __name__=="__main__":
    main()
