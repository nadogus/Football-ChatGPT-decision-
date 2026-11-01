"""Bridge runtime data into the deterministic evidence engine."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from football_evidence_engine import SourceDatum, MarketQuote, SOURCE_POLICY, build_evidence_packet

def _dt(value:str|None):
    if not value:return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z","+00:00"))

def source_datum(source:str,payload:dict[str,Any],observed_at:str|None=None):
    rel,age=SOURCE_POLICY.get(source,(.60,21600))
    return SourceDatum(source=source,observed_at=_dt(observed_at),reliability=rel,max_age_seconds=age,payload=payload)

def market_quotes(rows:list[dict[str,Any]],observed_at:str|None=None):
    out=[]
    for q in rows:
        try:
            out.append(MarketQuote(
                market=str(q.get("market") or ""),
                selection=str(q.get("selection") or ""),
                decimal_odds=float(q["decimal_odds"]),
                bookmaker=str(q.get("bookmaker") or q.get("source") or "unknown"),
                observed_at=_dt(q.get("observed_at") or observed_at),
                phase=str(q.get("phase") or "CURRENT"),
            ))
        except Exception:continue
    return out

def build_runtime_packet(*,match,models,source_payloads,odds_payload,league_coverage=1.0,xi=None,context=None,engine_version="evidence-v1.1"):
    sources=[]
    for item in source_payloads:
        if not item or not item.get("source"):continue
        sources.append(source_datum(str(item["source"]),item.get("data",item),item.get("observed_at")))
    odds_source=odds_payload.get("primary_source")
    if odds_source:
        source_name="flashscore:odds" if odds_source=="flashscore" else odds_source
        sources.append(source_datum(source_name,odds_payload,odds_payload.get("observed_at")))
    return build_evidence_packet(
        match=match,
        sources=sources,
        league_coverage=float(league_coverage),
        models=models,
        quotes=market_quotes(odds_payload.get("quotes",[]),odds_payload.get("observed_at")),
        xi=xi,
        context=context,
        engine_version=engine_version,
    )
