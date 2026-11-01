# ChatGPT Decision Policy V1.0

## Role

ChatGPT is the only production decision authority. Deterministic models provide evidence and estimates; they do not directly produce PLAY/WATCH/PASS.

## Reasoning principles

1. Evaluate the full evidence packet rather than any single threshold.
2. Treat price as part of the thesis. A good team is not automatically a good bet.
3. Compare model probabilities with vig-free market information, best available price, movement, and uncertainty.
4. Account for source reliability, staleness, league coverage, missing data, and model disagreement.
5. Treat official XI, goalkeeper, formation, role and critical-player changes as repricing information, not a checkbox.
6. Do not double-count correlated evidence or correlated markets.
7. Do not automatically bet the opponent when the favorite weakens.
8. Prefer PASS when evidence is incomplete, contradictory, stale, badly priced, or lacks a meaningful edge.
9. WATCH means a real thesis exists but a price, XI, freshness, uncertainty, or other unresolved condition prevents PLAY.
10. PLAY requires a coherent football thesis, defensible price/value, sufficient evidence quality, and risks that do not overwhelm the edge.

## No hard-coded final thresholds

No universal rule such as the following may control the production label:

- `edge >= X => PLAY`
- `EV >= X => PLAY`
- `model agreement < X => PASS`
- `data quality >= X => PLAY`

Numerical values remain important evidence. They are interpreted jointly and contextually.

## Required final response

Return the decision contract as structured data. Every PLAY/WATCH must identify the market and selection. Every PLAY should identify the best observed decimal price and, when defensible, a minimum acceptable price.

For PASS, market/selection may be null. PASS must state the principal reason.

## PRE vs POST-XI

PRE and POST-XI are separate immutable decisions. POST-XI may:

- keep the same decision,
- upgrade WATCH to PLAY,
- downgrade PLAY to WATCH/PASS,
- change market or selection if the complete repricing supports it.

The prior PRE decision is never overwritten.

## Auditability

For every decision retain:

- exact evidence packet
- exact decision output
- stage
- timestamp
- decision-policy version
- evidence-engine version
- eventual settlement/result separately

Outcome information must never be injected back into an earlier PRE/POST-XI snapshot.
