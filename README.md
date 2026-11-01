# Football ChatGPT Decision

## Mission

This repository is the experimental ChatGPT-led decision branch of the football pre-match system.

The original `Final-football-prematch` repository remains untouched and is the reference/master benchmark.

The governing architecture is defined in `EVIDENCE_FIRST_ARCHITECTURE.md` and the production reasoning policy in `CHATGPT_DECISION_POLICY.md`.

## Locked architecture

```text
DATA
  -> integrity / reliability / freshness / league coverage
  -> normalization + football features
  -> deterministic football models and calculations
  -> odds / devig / consensus / movement / EV
  -> PRE evidence packet
  -> ChatGPT PRE reasoning
  -> PRE decision snapshot
  -> official XI verification + player/GK/formation impact
  -> full POST-XI recalculation / repricing
  -> POST-XI evidence packet
  -> ChatGPT final reasoning
  -> PLAY / WATCH / PASS
  -> immutable ledger
```

## Core rule

**GitHub computes and organizes evidence. ChatGPT makes the final betting decision.**

GitHub should collect as much reliable, relevant and timely information as practical and perform the deterministic calculations that help ChatGPT reason. It must expose those observations and calculations rather than compressing them into a production recommendation.

There is no production hard-coded threshold such as `edge >= X => PLAY` or `agreement < Y => PASS`.

Deterministic calculations, rankings, gates and model outputs are evidence, not final authority. Existing deterministic logic is preserved when it is useful for calculations, integrity, diagnostics or shadow benchmarking.

## Preserved calculation layer

The system preserves, where available:

- source reliability and provenance
- freshness / staleness
- league coverage and data quality
- entity resolution
- schedule congestion
- xG / npxG context
- player availability
- player impact
- goalkeeper impact
- expected XI vs official XI delta
- Elo
- Poisson
- Dixon-Coles
- ensemble probabilities
- model disagreement/agreement
- devig
- market consensus
- best price
- odds movement
- fair odds
- edge and EV
- alternative market probabilities
- correlation-family metadata

## Decision authority

Only ChatGPT may assign the production decision:

- `PLAY`
- `WATCH`
- `PASS`

`PASS` is a correct outcome. The system must never force a bet.

ChatGPT reasons across the complete packet. A top-ranked candidate, positive EV, high agreement or strong data-quality score is never an automatic PLAY.

## PRE / POST-XI contract

A match can have two decision states:

1. `PRE` — decision based on the latest valid pre-match evidence.
2. `POST_XI` — complete re-evaluation after official lineups are verified and the evidence is repriced.

POST-XI does not merely confirm PRE. It may strengthen, weaken, change market, or cancel the previous view.

## Evidence packet

The handoff to ChatGPT must be machine-readable and contain at minimum:

- match identity and kickoff
- competition
- evidence timestamp
- stage (`PRE` or `POST_XI`)
- source provenance and freshness
- data-quality and coverage information
- team/model probabilities and component calculations
- model disagreement
- injuries / suspensions / availability
- XI and goalkeeper changes when known
- market quotes and bookmaker
- devigged market probabilities
- consensus and movement
- best prices
- fair prices
- edge / EV calculations
- correlation-family labels
- warnings / missing-data flags
- material uncertainty and contradictory evidence when available

The packet presents evidence; it does not contain the production recommendation.

## ChatGPT output contract

ChatGPT returns a structured decision containing:

- decision: `PLAY | WATCH | PASS`
- market and selection when applicable
- best decimal price
- minimum acceptable decimal price when applicable
- confidence
- concise rationale
- principal supporting evidence
- contradicting evidence / main risks
- material unknowns
- decision changers / unresolved conditions
- data-quality assessment
- stage
- timestamp
- engine/policy version

A `PASS` may have no market or selection.

## Safety / integrity rules

- Never fabricate missing data.
- Stale data must be labeled.
- Weak league coverage must be visible.
- Correlated markets must not be presented as independent evidence.
- A weakened favorite does not automatically create an opposite-side bet.
- Odds are decimal only in the decision interface.
- Results must never overwrite PRE or POST-XI snapshots.
- Mechanical benchmark decisions must not be shown to ChatGPT before the production decision is committed.

## Benchmarking

The legacy rule-based decision from the original system may be recorded as a **shadow benchmark only**. It has zero production decision authority in this repository and must remain isolated from ChatGPT's pre-decision evidence.

This allows an honest forward comparison between the old deterministic decision layer and the ChatGPT-led architecture without changing the original repository.
