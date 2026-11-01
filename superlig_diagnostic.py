"""One-off Super Lig source diagnostics. No betting decision."""
from __future__ import annotations
import json, urllib.parse
from data_adapters import FlashscoreClient, PinnaclePrematchClient, _json

out={}
fs=FlashscoreClient()

# raw helper through local Flashscore service
def local(path,params):
    try:
        return _json(fs.base+path+"?"+urllib.parse.urlencode(params))
    except Exception as e:
        return {"_error":f"{type(e).__name__}: {e}"}

out["search_fener"]=local("/search",{"query":"Fenerbahce","type":"team","sport":"football","limit":5})
out["search_goztepe"]=local("/search",{"query":"Goztepe","type":"team","sport":"football","limit":5})

def first_team_id(block):
    for r in (block.get("results") or []) if isinstance(block,dict) else []:
        if isinstance(r,dict) and r.get("id"): return r["id"]
    return None

for key in ["fener","goztepe"]:
    tid=first_team_id(out[f"search_{key}"])
    out[f"{key}_team_id"]=tid
    if tid:
        out[f"{key}_results"]=local("/teams/results",{"team":tid,"page":1})

try:
    pc=PinnaclePrematchClient()
    headers=pc._headers()
    out["pinnacle_leagues"]=_json(f"{pc.BASE}/sports/29/leagues?all=false",headers=headers)
except Exception as e:
    out["pinnacle_leagues"]={"_error":f"{type(e).__name__}: {e}"}

print(json.dumps(out,ensure_ascii=False,indent=2))
with open("SUPERLIG_DIAGNOSTIC.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
