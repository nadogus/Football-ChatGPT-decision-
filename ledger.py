"""Immutable pilot ledger.
PRE, POST_XI, FINAL and RESULT are separate append-only events. No overwrite API exists.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json

ALLOWED={"PRE_EVIDENCE","PRE_DECISION","POST_XI_EVIDENCE","FINAL_DECISION","RESULT"}

class PilotLedger:
    def __init__(self,path="ledger/pilot.jsonl"):
        self.path=Path(path)
    def append(self,event_type:str,match_id:str,payload:dict):
        if event_type not in ALLOWED: raise ValueError(f"invalid event_type: {event_type}")
        record={"event_type":event_type,"match_id":str(match_id),"written_at":datetime.now(timezone.utc).isoformat(),"payload":payload}
        canonical=json.dumps(record,sort_keys=True,separators=(",",":"),default=str)
        record["sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f:f.write(json.dumps(record,ensure_ascii=False,default=str)+"\n")
        return record
