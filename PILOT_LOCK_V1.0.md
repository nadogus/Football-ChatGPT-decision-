# Football ChatGPT Decision — V1.0 PILOT LOCK

Status: **FORWARD PILOT ACTIVE**
Target sample: **50 matches**

## Frozen architecture
`DATA -> integrity/reliability/freshness/coverage -> deterministic football calculations -> odds/devig/consensus/EV -> PRE evidence -> ChatGPT PRE decision -> confirmed official XI -> full repricing -> POST-XI evidence -> ChatGPT FINAL decision -> immutable ledger -> result/settlement`

## Decision authority
Only ChatGPT may assign production `PLAY / WATCH / PASS`. GitHub calculations are evidence only. No hard-coded threshold may silently become production decision authority during the pilot.

## Protection guards
1. Non-empty lineup payload alone never proves official XI.
2. POST-XI requires a plausible full starting XI and explicit confirmation or independent validation.
3. Unverified/predicted/partial XI remains PRE and fails closed.
4. Stale evidence remains visible and is never silently treated as current.
5. Missing data is never fabricated.
6. PRE, POST-XI, FINAL and RESULT are separate immutable events.
7. Results may not rewrite or influence earlier snapshots.
8. Correlated markets remain labeled as the same evidence family.
9. A weakened favorite never automatically creates an opposite-side bet.
10. `PASS` is a valid final outcome; no forced selection.

## Forward-test rules
- Count only decisions created before the result is known.
- Preserve exact evidence packet, policy version, engine version, price and timestamp.
- FINAL decision requires confirmed official XI when XI is available before kickoff.
- Record closing price when verifiable.
- Record W/L/Push/Void and flat-stake return for PLAY decisions.
- WATCH and PASS remain in the sample for calibration/decision-quality analysis but are not counted as placed bets.
- Original `Final-football-prematch` may be recorded as a SHADOW benchmark only and has zero authority over the new system's decision.

## Pilot success review
At 50 matches review: PLAY count, WATCH count, PASS count, hit rate, flat-stake ROI, price/CLV quality where available, PRE-to-POST-XI changes, data-quality distribution, false/late XI prevention, and decision calibration. Do not change the frozen architecture mid-pilot; urgent bug fixes must be documented separately.
