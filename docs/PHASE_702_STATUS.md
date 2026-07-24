# PHASE_702_STATUS

## What changed
The circular dependency is eliminated. `ResearchBelief` and `OperationalBelief` are independent
models with class-restricted evidence. Promotion is now five explicit states instead of a binary
flag. `LIMITED_DEMO_APPROVED` authorises evidence collection under a hard envelope, so operational
confidence can be earned without touching the live bar.

**No safety mechanism was weakened. No threshold was lowered. The live research bar remains 0.60.**

## Deliverables
`belief_graph_v2.py` · `operational_belief.py` · `promotion_pipeline_v2.py` · `demo_evidence.py` ·
`DEMO_PROMOTION_RULES.md` · `BELIEF_GRAPH_V2.md` · `test_phase702.py` (**11/11 pass**)

## Defect found and fixed during this phase
The first implementation let execution evidence accumulate into ResearchBelief: 50 clean demo trades
moved it 0.25 → 0.87 and perfect execution alone reached `LIVE_APPROVED`. Fixed with
`MAX_EXEC_RESEARCH_LOGODDS = 0.35`, a hard cap, now regression-tested.

## Current position
```
portfolio_multisleeve
  ResearchBelief    0.6133
  OperationalBelief 0.2523
  STATE             LIMITED_DEMO_APPROVED  (1 position, 0.1% risk, 3 trades/day)
  next              FULL_DEMO_APPROVED — needs operational ≥0.70 and ≥30 demo trades
```

## Remaining gaps
1. **`--demo-limited` is not yet wired into `portfolio_mt5.py`.** The envelope, evidence capture and
   promotion logic exist and are tested; the runner still uses the old `--live` path. **This is the
   next task and no demo trading should occur until it is done.**
2. **Execution records are not yet auto-populated from MT5.** `TradeExecutionRecord` fields must be
   filled from real order/deal data (retcode, fill price, spread at fill, latency) — currently they
   are constructed manually/in tests.
3. **Exit verification** remains unimplemented (rebalance-only, no exit reconciliation).
4. **Dashboard** does not yet render the two beliefs separately (spec item 6 outstanding).

## Unresolved risks
- OperationalBelief is only as honest as the checks that feed it; a check that is never populated
  reads as `False` and blocks promotion (fail-closed, but noisy).
- `MAX_EXEC_RESEARCH_LOGODDS` is a judgement value. It is deliberately conservative and
  change-controlled; raising it would re-open the leak.
- ResearchBelief 0.6133 rests on a single walk-forward study minus one audit correction. It is above
  the live bar on paper, but LIVE also requires operational ≥0.85 and 100 clean demo trades.
