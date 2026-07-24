# BELIEF_GRAPH_V2 — two independent beliefs

## Why two
A single belief created a deadlock: live execution was blocked until belief rose, but belief could
only rise from execution evidence. The fix is not a lower bar — it is recognising that
**"does this have edge?"** and **"does this execute correctly?"** are different questions with
different evidence.

| | ResearchBelief | OperationalBelief |
|--|--|--|
| answers | does the strategy have statistical edge? | does the system execute correctly? |
| prior | 0.25 | 0.20 (assume execution broken until shown) |
| inputs | walk-forward, bootstrap CI, after-cost perf, replication, parameter stability, GT-Score, economic rationale | broker-side stop, symbol mapping, fill reconciliation, latency, slippage, sizing, ledger consistency, duplicate detection, lifecycle integrity, guardian approval, broker acks |
| changes | slowly, from research work | only from demo/live execution |

## Evidence classes and permitted influence
| class | → ResearchBelief | → OperationalBelief |
|--|--|--|
| Backtest | 0.60 | 0.00 |
| WalkForward | 1.00 | 0.00 |
| Bootstrap | 0.80 | 0.00 |
| Shadow | 0.00 | 0.50 |
| DemoExecution | 0.10 *(capped)* | 1.00 |
| LiveExecution | 0.15 *(capped)* | 1.00 |

## The cap (the critical safeguard)
`MAX_EXEC_RESEARCH_LOGODDS = 0.35`. Execution-derived evidence has a **hard ceiling** on its total
influence on ResearchBelief. Without it, many individually-small nudges accumulate: in testing,
50 clean demo trades moved ResearchBelief 0.25 → 0.87, and flawless execution alone bought
`LIVE_APPROVED`. That is the leak this design forbids — **good execution must never buy
edge-confidence.** Proven by `test_demo_execution_cannot_inflate_research_belief_materially` and
`test_state_live_requires_unchanged_060_research_bar`.

## Current state — portfolio_multisleeve
```
ResearchBelief    0.6133   (walk-forward + shadow, minus the prop-audit correction)
OperationalBelief 0.2523   (no demo trades yet — execution unproven)
STATE             LIMITED_DEMO_APPROVED   (1 position, 0.1% risk)
Blocking FULL_DEMO: operational_belief 0.2523 < 0.70 · demo_trades 0 < 30
```
