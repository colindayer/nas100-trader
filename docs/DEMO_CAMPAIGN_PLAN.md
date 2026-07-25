# DEMO_CAMPAIGN_PLAN — evidence campaign, not a trading attempt

## Goal
Produce **30 fully-evidenced executions** proving the machine works. P&L is not a goal and is not a
success criterion. The previous account lost 4.9% and produced almost no usable evidence — that is
the failure being corrected.

## Configuration (fixed for the whole campaign)
One strategy · one symbol · `--demo-limited` · 1 position · 0.10% risk · 3 trades/day · demo only.
**No configuration changes mid-campaign.** A change ends the campaign and starts a new one.

## Success criteria
| dimension | criterion |
|--|--|
| Execution correctness | 100% of fills carry a verified broker-side stop |
| Ledger integrity | 100% of fills have a ledger entry created **before** submission |
| Reconciliation | 100% of startups reconcile clean; 0 orphans |
| Persistence | ≥1 **observed** restart mid-campaign with counter and halt preserved |
| Governance | 0 executions without promotion-state authorisation |
| Drawdown | < 3% total, no single day > 1% |
| Evidence | ≥30 `DemoExecution` records with complete spread/slippage/latency fields |

## Daily checklist
Morning: verify → scan-executors → healthcheck → startup → shadow book.
During: after each fill, confirm SL present, volume correct, magic/comment correct, ledger entry, reconciliation passed.
Evening: `reaction_recorder --summary`; read the audit log; record incidents.

## Weekly review
Trades, fills, defects, halts (and time-to-detect), operational belief movement, healthcheck history,
deployment drift. Written up even if uneventful.

## Evidence to collect
Per trade: expected vs actual entry · spread at fill · slippage · latency · retcode · stop verified ·
reconciliation result · defects. Per day: healthcheck output, startup diagnostics, audit log.

## Manual review process
**The first five fills are reviewed one at a time before the next is permitted.** After that, daily
review. Any unexplained execution stops the campaign immediately.

## Kill criteria (end the campaign)
Any orphan position · any naked fill · any duplicate execution · any unexplained execution ·
any state corruption not auto-recovered · drawdown > 3% · a halt that fails to persist ·
any governance bypass.

## Promotion criteria (LIMITED_DEMO → FULL_DEMO)
Operational belief ≥ 0.70 **and** ≥30 demo trades **and** 0 outstanding defects — computed by
`promotion_pipeline_v2`, never asserted by hand. **These thresholds are not negotiable during a
campaign.**
