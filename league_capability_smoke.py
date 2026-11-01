"""Multi-league capability smoke test.

This is evidence coverage testing only. It never makes a betting decision.
Each league is independently classified by the generic competition resolver as
SUPPORTED / PARTIAL / UNSUPPORTED. A league failure does not abort the matrix.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from competition_resolver import league_capability

CASES = [
    {"league": "English Premier League", "home": "Liverpool", "away": "Arsenal"},
    {"league": "Turkish Super Lig", "home": "Fenerbahce", "away": "Galatasaray"},
    {"league": "LaLiga", "home": "Barcelona", "away": "Real Madrid"},
    {"league": "Serie A", "home": "Inter", "away": "AC Milan"},
    {"league": "Bundesliga", "home": "Bayern Munich", "away": "Borussia Dortmund"},
    {"league": "Ligue 1", "home": "Paris SG", "away": "Marseille"},
    {"league": "Eredivisie", "home": "Ajax", "away": "PSV"},
    {"league": "Primeira Liga", "home": "Benfica", "away": "FC Porto"},
]


def main() -> None:
    # Capability checks need a cutoff after recent completed matches, not a fixture ID.
    as_of = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
    rows = []
    for case in CASES:
        try:
            result = league_capability(
                home=case["home"],
                away=case["away"],
                competition=case["league"],
                kickoff=as_of,
            )
            rows.append({**case, **result})
        except Exception as exc:
            rows.append({
                **case,
                "status": "UNSUPPORTED",
                "checks": {},
                "details": {"exception": f"{type(exc).__name__}: {exc}"},
            })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_type": "LEAGUE_CAPABILITY_SMOKE_V1",
        "decision_authority": "CHATGPT_ONLY",
        "production_decision": None,
        "counts": {
            "SUPPORTED": sum(r.get("status") == "SUPPORTED" for r in rows),
            "PARTIAL": sum(r.get("status") == "PARTIAL" for r in rows),
            "UNSUPPORTED": sum(r.get("status") == "UNSUPPORTED" for r in rows),
        },
        "leagues": rows,
    }
    Path("LEAGUE_CAPABILITY_SMOKE.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # The matrix itself must complete; individual unsupported leagues are valid findings.
    if len(rows) != len(CASES):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
