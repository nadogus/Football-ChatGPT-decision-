"""Automated evidence collection for Football ChatGPT Decision.

Collects external evidence and normalizes it for the deterministic evidence engine.
It NEVER assigns PLAY/WATCH/PASS. Missing providers are returned as explicit gaps.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
import os

from data_adapters import (
    AdapterResult, ESPNLineupClient, FotMobLineupClient, FlashscoreClient,
    PinnaclePrematchClient, OddsHarvesterClient, normalize_decimal_quotes,
)

COLLECTOR_VERSION = "EVIDENCE_COLLECTOR_V1.0"


def _result(r: AdapterResult) -> dict[str, Any]:
    return {"source": r.source, "ok": r.ok, "observed_at": r.observed_at, "data": r.data, "error": r.error}


def _gap(source: str, reason: str) -> dict[str, Any]:
    return {"source": source, "ok": False, "observed_at": datetime.now(timezone.utc).isoformat(), "data": {}, "error": reason}


def collect_match_evidence(*, match: dict[str, Any], provider_ids: dict[str, Any] | None = None,
                           pinnacle_league_id: int | None = None, date_yyyymmdd: str | None = None,
                           odds_league: str | None = None) -> dict[str, Any]:
    """Collect every configured source independently; never hide a failure.

    provider_ids may contain: espn_league_slug, espn_event_id, fotmob_match_id,
    flashscore_match_id, pinnacle_matchup_id.
    """
    ids = provider_ids or {}
    evidence: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []
    lineup_evidence: list[dict[str, Any]] = []

    # ESPN match/lineup context
    if ids.get("espn_league_slug") and ids.get("espn_event_id"):
        r = ESPNLineupClient().summary(str(ids["espn_league_slug"]), str(ids["espn_event_id"]))
        evidence.append(_result(r))
        if r.ok:
            lineup_evidence.append({"source": "espn", "starter_ids": ESPNLineupClient.lineup_ids(r.data), "observed_at": r.observed_at})
    else:
        evidence.append(_gap("espn", "ESPN_PROVIDER_IDS_MISSING"))

    # FotMob match/lineup context
    if ids.get("fotmob_match_id"):
        r = FotMobLineupClient().match_details(str(ids["fotmob_match_id"]))
        evidence.append(_result(r))
        if r.ok:
            lineup_evidence.append({"source": "fotmob", "starter_ids": FotMobLineupClient.lineup_ids(r.data), "observed_at": r.observed_at})
    else:
        evidence.append(_gap("fotmob", "FOTMOB_MATCH_ID_MISSING"))

    # Flashscore details / lineup / odds when a configured bridge exists.
    if ids.get("flashscore_match_id"):
        fs = FlashscoreClient()
        for label, r in (("details", fs.details(str(ids["flashscore_match_id"]))),
                         ("lineups", fs.lineups(str(ids["flashscore_match_id"]))),
                         ("odds", fs.odds(str(ids["flashscore_match_id"])))):
            d = _result(r); d["kind"] = label; evidence.append(d)
            if label == "odds" and r.ok:
                quotes.extend(normalize_decimal_quotes(r.data, "flashscore"))
    else:
        evidence.append(_gap("flashscore", "FLASHSCORE_MATCH_ID_MISSING"))

    # Pinnacle prices when configured.
    if pinnacle_league_id is not None:
        r = PinnaclePrematchClient().odds(int(pinnacle_league_id), ids.get("pinnacle_matchup_id"))
        evidence.append(_result(r))
        if r.ok: quotes.extend(normalize_decimal_quotes(r.data, "pinnacle"))
    else:
        evidence.append(_gap("pinnacle", "PINNACLE_LEAGUE_ID_MISSING"))

    # OddsHarvester provides a second independent odds path when installed.
    if date_yyyymmdd:
        r = OddsHarvesterClient().upcoming(date_yyyymmdd, league=odds_league)
        evidence.append(_result(r))
        if r.ok: quotes.extend(normalize_decimal_quotes(r.data, "oddsharvester"))
    else:
        evidence.append(_gap("oddsharvester", "MATCH_DATE_MISSING"))

    # Preserve all source failures. ChatGPT must see what was unavailable.
    gaps = [{"source": x["source"], "reason": x.get("error") or "UNKNOWN"} for x in evidence if not x.get("ok")]
    successful = [x["source"] for x in evidence if x.get("ok")]
    return {
        "collector_version": COLLECTOR_VERSION,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "match": match,
        "source_results": evidence,
        "lineup_evidence": lineup_evidence,
        "odds_payload": {
            "primary_source": "multi_source",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "quotes": quotes,
        },
        "collection_status": {
            "successful_sources": sorted(set(successful)),
            "gaps": gaps,
            "quote_count": len(quotes),
            "lineup_source_count": len(lineup_evidence),
        },
    }


def packet_inputs(collection: dict[str, Any]) -> dict[str, Any]:
    """Convert collector output to build_runtime_packet-compatible inputs."""
    source_payloads = []
    for x in collection.get("source_results", []):
        if x.get("ok"):
            source_payloads.append({"source": x["source"], "observed_at": x.get("observed_at"), "data": x.get("data", {})})
    context = {
        "collector_version": collection.get("collector_version"),
        "collection_status": collection.get("collection_status", {}),
        "lineup_evidence": collection.get("lineup_evidence", []),
    }
    return {"source_payloads": source_payloads, "odds_payload": collection.get("odds_payload", {}), "context": context}
