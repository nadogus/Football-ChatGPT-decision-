> Not (Kasım 2026): Bu belge ilk mimariyi anlatır. Güncel çalışan hat için README.md'ye bakın; Pinnacle, Transfermarkt ve eski orkestrasyon modülleri kaldırılmıştır.

# Evidence-First Architecture V2.0

## Purpose

This repository exists to prepare the best possible pre-match decision table for ChatGPT. GitHub is not the production betting decision-maker.

## Division of responsibility

### GitHub / deterministic layer

GitHub may and should do as much deterministic work as possible:

- collect data from available sources;
- preserve source provenance and timestamps;
- normalize entities, competitions, teams, players, markets and prices;
- score source reliability, freshness, staleness and league coverage;
- calculate football features and contextual metrics;
- run Poisson, Dixon-Coles, Elo, xG/npxG, ensemble and other deterministic models;
- calculate devigged market probabilities, consensus, movement, fair prices, edge and EV;
- calculate player, goalkeeper, formation and official-XI impacts;
- expose alternative markets and correlation families;
- identify missing, stale, conflicting or weak evidence;
- preserve PRE and POST-XI snapshots and all deterministic calculations in the immutable ledger.

These calculations are evidence. They are not the production decision.

### ChatGPT / reasoning layer

ChatGPT receives the complete evidence packet and is the sole production decision authority. It must reason across the evidence jointly rather than execute a single threshold or score.

ChatGPT must consider, where available:

- strength and provenance of the underlying data;
- freshness and coverage;
- agreement and disagreement among models;
- football context and causal plausibility;
- injuries, suspensions, expected XI, official XI, goalkeeper, roles and formation;
- market price, vig-free probabilities, consensus and movement;
- edge/EV calculations and their uncertainty;
- correlated evidence and correlated markets;
- contradictions, missing information and unresolved conditions.

ChatGPT may return PLAY, WATCH or PASS. PASS is a valid successful decision. WATCH means the thesis is unresolved and must identify what would resolve it when possible.

## Non-negotiable rule

No deterministic module in this repository may have production authority to convert evidence into PLAY/WATCH/PASS through a universal rule such as `edge >= X => PLAY`.

Existing deterministic rules, calculations, gates and model outputs are preserved as evidence, integrity controls, diagnostics or shadow benchmarks. They must not be deleted merely because ChatGPT owns the final decision.

## Handoff principle

The evidence packet should answer four questions for ChatGPT:

1. **What do we know?** Raw/normalized observations, provenance and timestamps.
2. **What did the deterministic layer calculate?** Models, probabilities, prices, edge/EV and derived features.
3. **What is uncertain or conflicting?** Missing data, stale data, disagreement, contradictory signals and coverage weaknesses.
4. **What changed?** Especially between PRE and POST-XI, including repricing caused by official lineups.

The packet must not answer a fifth question — **What should we bet?** — because that is ChatGPT's responsibility.

## Production flow

```text
SOURCES
  -> collection + provenance
  -> normalization
  -> integrity / reliability / freshness / coverage
  -> deterministic football calculations and models
  -> market / devig / consensus / movement / fair price / edge / EV
  -> PRE evidence packet
  -> ChatGPT PRE reasoning
  -> PRE decision snapshot
  -> official XI verification
  -> full POST-XI recalculation / repricing
  -> POST-XI evidence packet
  -> ChatGPT POST-XI reasoning
  -> FINAL decision snapshot
  -> immutable ledger + later settlement
```

## Anti-black-box requirement

ChatGPT's final output must remain auditable. The decision should state the main supporting evidence, contradicting evidence/main risks, data-quality assessment and, for WATCH or conditional views, what information or price change could change the decision.

## Benchmarking

A legacy or mechanical rule engine may run only as a shadow benchmark. Its output must be stored separately and must never be injected into the ChatGPT evidence packet in a way that anchors the production decision. This permits an honest forward comparison of deterministic and ChatGPT-led decision quality.

## Repository boundary

This architecture applies to `Football-ChatGPT-decision-`. It does not modify or redefine other football repositories.