from datetime import datetime, timezone

from data_adapters import normalize_decimal_quotes
from football_evidence_engine import MarketQuote, build_evidence_packet, elo_1x2, scoreline_markets, SourceDatum
from market_evidence import (closing_line_value, devig_power, market_fair_probability, market_summary)

NOW = datetime.now(timezone.utc)


def _fs_payload():
    def sel(s, v, o, h=None):
        return {"selection": s, "value": v, "opening_value": o, "handicap": h}
    return {"markets": [
        {"bookmaker": {"name": "bet365"}, "bet_type": "HOME_DRAW_AWAY", "bet_scope": "FULL_TIME",
         "selections": [sel("home", 2.10, 2.30), sel("draw", 3.40, 3.30), sel("away", 3.60, 3.25)]},
        {"bookmaker": {"name": "Pinnacle"}, "bet_type": "HOME_DRAW_AWAY", "bet_scope": "FULL_TIME",
         "selections": [sel("home", 2.18, 2.40), sel("draw", 3.50, 3.45), sel("away", 3.70, 3.20)]},
        {"bookmaker": {"name": "bet365"}, "bet_type": "OVER_UNDER", "bet_scope": "FULL_TIME",
         "selections": [sel("over", 1.90, 2.00, {"value": "2.5"}), sel("under", 1.90, 1.80, {"value": "2.5"})]},
        {"bookmaker": {"name": "bet365"}, "bet_type": "HOME_DRAW_AWAY", "bet_scope": "FIRST_HALF",
         "selections": [sel("home", 9.0, 9.0)]},
    ]}


def test_moneyline_quotes_now_produce_consensus():
    """V1 bug: consensus looked for '1X2' but adapters emit 'moneyline' -> always empty."""
    quotes = normalize_decimal_quotes(_fs_payload(), "flashscore")
    assert {q["market"] for q in quotes} >= {"moneyline"}
    s = market_summary(quotes)
    assert s["1x2"]["bookmakers"] == 2
    assert abs(sum(s["1x2"]["consensus_fair"].values()) - 1) < 1e-3
    assert s["1x2"]["pinnacle_fair"] is not None


def test_opening_and_current_give_movement_and_best_price_ignores_opening():
    quotes = normalize_decimal_quotes(_fs_payload(), "flashscore", include_opening=True)
    phases = {q["phase"] for q in quotes}
    assert phases == {"CURRENT", "OPENING"}
    s = market_summary(quotes)
    mv = s["1x2"]["movement_pp"]
    assert mv["HOME"] > 0 and mv["AWAY"] < 0  # home shortened 2.30 -> 2.10
    # best price must be a current price (opening 2.40 is no longer available)
    assert s["1x2"]["best_price"]["HOME"]["odds"] == 2.18
    assert s["totals"]["2.5"]["consensus_fair"]["OVER"] == 0.5


def test_first_half_markets_excluded():
    quotes = normalize_decimal_quotes(_fs_payload(), "flashscore")
    assert all(q["decimal_odds"] != 9.0 for q in quotes)


def test_power_devig():
    p = devig_power({"HOME": 1.5, "DRAW": 4.2, "AWAY": 7.0})
    assert abs(sum(p.values()) - 1) < 1e-9
    assert p["AWAY"] < (1 / 7.0) / sum(1 / x for x in (1.5, 4.2, 7.0))


def test_packet_has_market_comparison_and_no_decision():
    rows = normalize_decimal_quotes(_fs_payload(), "flashscore", include_opening=True)
    quotes = [MarketQuote(q["market"], q["selection"], q["decimal_odds"], q["bookmaker"], NOW, q.get("phase", "CURRENT")) for q in rows]
    p = build_evidence_packet(match={"id": "x"}, sources=[SourceDatum("flashscore", NOW, .8, 900)], league_coverage=1.0,
                              models={"dc": scoreline_markets(1.5, 1.1), "elo": elo_1x2(1650, 1600)}, quotes=quotes)
    assert p["market"]["consensus_1x2"]
    c = {r["selection"]: r for r in p["market"]["candidates"]}
    assert c["HOME"]["market_fair_probability"] is not None
    assert c["HOME"]["model_minus_market_pp"] is not None
    assert all(r["best_odds"] != 2.40 for r in p["market"]["candidates"])
    assert p["production_decision"] is None


def test_clv():
    assert closing_line_value(2.20, 0.50) == 0.1
    assert closing_line_value(2.20, None) is None
    s = market_summary(normalize_decimal_quotes(_fs_payload(), "flashscore"))
    assert market_fair_probability(s, "OVER_2.5") == 0.5
    assert market_fair_probability(s, "HOME_DNB") is None
