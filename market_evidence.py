"""Market evidence: vig-free probabilities, consensus, Pinnacle fair price, best price
and opening -> current movement. Evidence only; never assigns PLAY/WATCH/PASS.

Fixes the V1 bug where consensus searched for market "1X2" while every adapter
emits "moneyline", so `consensus_1x2` was always empty.
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable

MARKET_ALIASES = {"1x2": "1X2", "moneyline": "1X2", "home_draw_away": "1X2", "match_odds": "1X2",
                  "total": "TOTAL", "over_under": "TOTAL", "totals": "TOTAL",
                  "dnb": "DNB", "draw_no_bet": "DNB"}
ONE_X_TWO = ("HOME", "DRAW", "AWAY")
SHARP_BOOKS = ("pinnacle",)
TOTAL_LINES_KEPT = ("1.5", "2.5", "3.5")


def canonical_market(name: Any) -> str:
    return MARKET_ALIASES.get(str(name or "").strip().lower(), str(name or "").strip().upper())


def _get(q, key, default=None):
    return q.get(key, default) if isinstance(q, dict) else getattr(q, key, default)


def quote_rows(quotes: Iterable[Any]) -> list[dict[str, Any]]:
    """Dicts or MarketQuote objects -> uniform dict rows with canonical market names."""
    out = []
    for q in quotes or []:
        try:
            odds = float(_get(q, "decimal_odds"))
        except (TypeError, ValueError):
            continue
        if not odds > 1.0:
            continue
        out.append({"market": canonical_market(_get(q, "market")),
                    "selection": str(_get(q, "selection") or "").upper(),
                    "decimal_odds": odds,
                    "bookmaker": str(_get(q, "bookmaker") or "unknown"),
                    "phase": str(_get(q, "phase") or "CURRENT").upper()})
    return out


def devig_multiplicative(odds: dict[str, float]) -> dict[str, float]:
    raw = {k: 1.0 / v for k, v in odds.items()}
    z = sum(raw.values())
    return {k: v / z for k, v in raw.items()}


def devig_power(odds: dict[str, float], iters: int = 60) -> dict[str, float]:
    """p_i = q_i^k with sum 1; shrinks longshots more than favourites."""
    q = {k: 1.0 / v for k, v in odds.items()}
    if sum(q.values()) <= 1.0:
        return devig_multiplicative(odds)
    lo, hi = 1.0, 3.0
    for _ in range(iters):
        k = (lo + hi) / 2
        s = sum(v ** k for v in q.values())
        lo, hi = (k, hi) if s > 1 else (lo, k)
    k = (lo + hi) / 2
    p = {s: v ** k for s, v in q.items()}
    z = sum(p.values())
    return {s: v / z for s, v in p.items()}


def _book_tables(rows, market, phase, line=None):
    """{bookmaker: {selection: odds}} for one market/phase (and totals line)."""
    books: dict[str, dict[str, float]] = {}
    for r in rows:
        if r["market"] != market or r["phase"] != phase:
            continue
        sel = r["selection"]
        if market == "TOTAL":
            side, _, ln = sel.partition("_")
            if ln != line or side not in ("OVER", "UNDER"):
                continue
            sel = side
        books.setdefault(r["bookmaker"], {})[sel] = r["decimal_odds"]
    return books


def _summarize(books: dict[str, dict[str, float]], selections: tuple[str, ...]) -> dict[str, Any] | None:
    complete = {b: o for b, o in books.items() if all(s in o for s in selections)}
    if not complete:
        return None
    fair = {b: devig_power(o) for b, o in complete.items()}
    overround = {b: round(sum(1 / v for v in o.values()) - 1, 4) for b, o in complete.items()}
    consensus = {s: statistics.median(f[s] for f in fair.values()) for s in selections}
    z = sum(consensus.values())
    consensus = {s: round(v / z, 4) for s, v in consensus.items()}
    best = {}
    for s in selections:
        b, o = max(((b, o[s]) for b, o in complete.items()), key=lambda x: x[1])
        best[s] = {"odds": o, "bookmaker": b, "fair_odds_consensus": round(1 / consensus[s], 3),
                   "ev_vs_consensus": round(o * consensus[s] - 1, 4)}
    sharp = next((b for b in complete if b.strip().lower() in SHARP_BOOKS), None)
    return {"bookmakers": len(complete),
            "consensus_fair": consensus,
            "pinnacle_fair": {s: round(v, 4) for s, v in fair[sharp].items()} if sharp else None,
            "best_price": best,
            "median_overround": round(statistics.median(overround.values()), 4),
            "devig_method": "power, median across bookmakers"}


def _with_movement(current, opening, selections):
    if current and opening:
        current["opening_consensus_fair"] = opening["consensus_fair"]
        current["movement_pp"] = {s: round(100 * (current["consensus_fair"][s] - opening["consensus_fair"][s]), 2)
                                  for s in selections}
    elif current:
        current["opening_consensus_fair"] = None
        current["movement_pp"] = None
    return current


def market_summary(quotes: Iterable[Any]) -> dict[str, Any]:
    """Market section of the evidence packet."""
    rows = quote_rows(quotes)
    out: dict[str, Any] = {"quote_count": len(rows),
                           "phases": sorted({r["phase"] for r in rows})}
    cur = _summarize(_book_tables(rows, "1X2", "CURRENT"), ONE_X_TWO)
    opn = _summarize(_book_tables(rows, "1X2", "OPENING"), ONE_X_TWO)
    out["1x2"] = _with_movement(cur, opn, ONE_X_TWO)
    lines = sorted({r["selection"].partition("_")[2] for r in rows
                    if r["market"] == "TOTAL" and r["selection"].startswith(("OVER_", "UNDER_"))},
                   key=lambda x: float(x) if x.replace(".", "", 1).isdigit() else 99)
    totals = {}
    for ln in lines:
        c = _summarize(_book_tables(rows, "TOTAL", "CURRENT", ln), ("OVER", "UNDER"))
        o = _summarize(_book_tables(rows, "TOTAL", "OPENING", ln), ("OVER", "UNDER"))
        if c:
            totals[ln] = _with_movement(c, o, ("OVER", "UNDER"))
    # keep the standard lines plus the most balanced one (21 lines bloated every packet ~4x)
    if totals:
        main = min(totals, key=lambda k: abs(totals[k]["consensus_fair"]["OVER"] - 0.5))
        totals = {k: v for k, v in totals.items() if k in TOTAL_LINES_KEPT or k == main}
        out["main_total_line"] = main
    out["totals"] = totals
    return out


def market_fair_probability(summary: dict[str, Any], selection: str) -> float | None:
    """Consensus vig-free probability for an engine selection key (HOME, OVER_2.5, ...)."""
    sel = selection.upper()
    if sel in ONE_X_TWO and summary.get("1x2"):
        return summary["1x2"]["consensus_fair"].get(sel)
    side, _, ln = sel.partition("_")
    t = (summary.get("totals") or {}).get(ln)
    if side in ("OVER", "UNDER") and t:
        return t["consensus_fair"].get(side)
    return None


def closing_line_value(price: float, closing_fair_probability: float | None) -> float | None:
    """CLV = price taken x vig-free closing probability - 1 (expected return at the close)."""
    if not closing_fair_probability or not price or price <= 1:
        return None
    return round(price * closing_fair_probability - 1, 4)
