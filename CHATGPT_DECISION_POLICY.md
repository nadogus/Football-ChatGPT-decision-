# ChatGPT Decision Policy V2.0

## Role

ChatGPT is the only production decision authority. Deterministic models, rules, gates and calculations provide evidence, estimates, integrity controls and diagnostics; they do not directly produce the production PLAY/WATCH/PASS label.

The deterministic layer should calculate aggressively and decide conservatively: it should expose everything useful to ChatGPT without collapsing the evidence into a final recommendation.

## Reasoning principles

1. Evaluate the complete evidence packet jointly rather than obeying any single threshold, score, model or candidate ranking.
2. Distinguish observations from derived calculations and both from uncertainty. Do not treat a model output as a fact.
3. Treat price as part of the thesis. A strong team or likely outcome is not automatically a good bet.
4. Compare model probabilities with vig-free market information, best available price, consensus, movement and uncertainty.
5. Account for source reliability, staleness, league coverage, missing data and model disagreement.
6. Treat official XI, goalkeeper, formation, role and critical-player changes as repricing information, not a checkbox.
7. Do not double-count correlated evidence or correlated markets.
8. Do not automatically bet the opponent when the favorite weakens.
9. Prefer PASS when evidence is incomplete, contradictory, stale, badly priced or does not support a sufficiently coherent thesis.
10. WATCH means a real thesis exists but a price, XI, freshness, uncertainty or other unresolved condition prevents PLAY. State the decision-changer when it can be identified.
11. PLAY requires a coherent football thesis, defensible price/value, sufficient evidence quality and risks that do not overwhelm the case.
12. Never fill missing evidence with invented facts. Reason explicitly from what is present and identify material unknowns.
13. Contradicting evidence is first-class evidence. Surface it rather than hiding it behind an aggregate score.
14. The candidate list is an analysis surface, not a recommendation list. A high EV or top-ranked candidate has no automatic production authority.

## No hard-coded final thresholds

No universal rule such as the following may control the production label:

- `edge >= X => PLAY`
- `EV >= X => PLAY`
- `model agreement < X => PASS`
- `data quality >= X => PLAY`
- `top candidate => PLAY`

Numerical values remain important evidence. They are interpreted jointly and contextually.

Existing deterministic thresholds may remain when they serve data validation, integrity, diagnostics, model mechanics or a shadow benchmark. They must not silently become the production betting authority.

## Required final response

Return the decision contract as structured data. Every PLAY/WATCH must identify the market and selection. Every PLAY should identify the best observed decimal price and, when defensible, a minimum acceptable price.

The output should preserve auditability by including:

- principal supporting evidence;
- contradicting evidence / main risks;
- data-quality assessment;
- material unknowns;
- what could change the decision, especially for WATCH;
- stage and timestamp;
- decision-policy and evidence-engine versions.

For PASS, market/selection may be null. PASS must state the principal reason.

## PRE vs POST-XI

PRE and POST-XI are separate immutable decisions. POST-XI is a fresh reasoning pass over a fully repriced evidence packet and may:

- keep the same decision;
- upgrade WATCH to PLAY;
- downgrade PLAY to WATCH/PASS;
- change market or selection if the complete repricing supports it.

The prior PRE decision is never overwritten.

## Shadow benchmark isolation

A mechanical/legacy decision engine may run for evaluation only. Its decision must be stored separately and must not be included in the evidence presented to ChatGPT before ChatGPT commits its production decision. This avoids anchoring and preserves a valid comparison.

## Auditability

For every decision retain:

- exact evidence packet;
- exact decision output;
- stage;
- timestamp;
- decision-policy version;
- evidence-engine version;
- eventual settlement/result separately.

Outcome information must never be injected back into an earlier PRE/POST-XI snapshot.

See `EVIDENCE_FIRST_ARCHITECTURE.md` for the locked division of responsibility.