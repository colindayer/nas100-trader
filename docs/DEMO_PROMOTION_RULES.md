# DEMO_PROMOTION_RULES — five states, explicit requirements

| state | research ≥ | operational ≥ | demo trades ≥ | defects | positions | risk/trade | purpose |
|--|--|--|--|--|--|--|--|
| RESEARCH_ONLY | — | — | — | — | 0 | 0 | default; no execution |
| SHADOW_APPROVED | 0.40 | — | 0 | 0 | 0 | 0 | observe; places nothing |
| **LIMITED_DEMO_APPROVED** | **0.50** | — | 0 | 0 | **1** | **0.10%** | **collect operational evidence** |
| FULL_DEMO_APPROVED | 0.55 | 0.70 | 30 | 0 | 3 | 0.50% | execution proven over a sample |
| **LIVE_APPROVED** | **0.60 (UNCHANGED)** | 0.85 | 100 | 0 | 15 | 1.00% | real edge AND proven execution |

## Why LIMITED_DEMO at 0.50 is not "lowering the threshold"
The 0.60 bar governs **risking real capital** and is unchanged. The 0.50 bar governs **whether a
strategy deserves further evaluation** on an account where no money is at risk. Different question,
different bar, both explicit. `test_state_live_requires_unchanged_060_research_bar` asserts the live
value is exactly 0.60 and fails if anyone edits it.

## Limited demo envelope (`--demo-limited`)
Demo account only · max 1 concurrent position · 0.1% risk · max 3 trades/day · Guardian approval on
every trade · **automatic shutdown on any critical error** · every trade updates OperationalBelief ·
never meaningfully updates ResearchBelief.

Critical checks (failure = defect = halt): `stop_verified`, `reconciliation_passed`,
`ledger_recorded`, `no_duplicate`.

## Recorded per demo trade
expected/actual entry · expected/actual spread · expected/actual slippage · stop verified · exit
verified · reconciliation passed · execution latency · broker retcode · operational defects.
**P&L is deliberately not an operational input** — profit does not prove the machine works.
