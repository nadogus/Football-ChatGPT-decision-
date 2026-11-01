"""Diagnostics for public model-input sources. No secrets, no decisions."""
from __future__ import annotations
import json,re,urllib.request
from public_sources import _text

def probe(url):
    out={"url":url}
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=15) as r:
            body=r.read().decode("utf-8",errors="replace")
            out.update({
                "ok":True,
                "status":getattr(r,"status",None),
                "length":len(body),
                "has_datesData":"datesData" in body,
                "has_JSON_parse":"JSON.parse" in body,
                "has_vegaJson":"vegaJson" in body,
                "script_vars":sorted(set(re.findall(r"var\\s+([A-Za-z0-9_]+)\\s*=",body)))[:50],
                "json_parse_contexts":[
                    re.sub(r"\\s+"," ",body[max(0,m.start()-120):min(len(body),m.start()+220)])
                    for m in list(re.finditer(r"JSON\\.parse",body))[:12]
                ],
            })
    except Exception as e:
        out.update({"ok":False,"error":f"{type(e).__name__}: {e}"})
    return out

report={
    "understat_2025":probe("https://understat.com/team/Liverpool/2025"),
    "clubelo_api_https":probe("https://api.clubelo.com/Liverpool"),
    "clubelo_api_http":probe("http://api.clubelo.com/Liverpool"),
    "clubelo_web":probe("https://clubelo.com/Liverpool"),
}
print(json.dumps(report,indent=2))
with open("MODEL_SOURCE_DIAGNOSTICS.json","w") as f:json.dump(report,f,indent=2)
