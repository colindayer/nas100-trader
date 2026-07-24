# PHASE_702_1_STATUS — Limited Demo execution wired

**Scope respected:** no change to the Belief Graph, research thresholds, promotion rules, Guardian,
execution-safety architecture, posterior calculations, or approval criteria. `REQUIREMENTS
["LIVE_APPROVED"]["research_min"]` is still **0.60**, asserted by `test_live_research_bar_unchanged`.

## What was wired
`scripts/portfolio_mt5.py` → `run_demo_limited()`, reached via **`--demo-limited`**. It uses the
**promotion pipeline**, not the legacy `--live` path.

Enforced envelope, exactly as configured by the strategy's promotion state:

| control | implementation |
|--|--|
| refuse unless ≥ LIMITED_DEMO_APPROVED | `evaluate(SID)` → halts if `not may_trade_demo` |
| max 1 concurrent position | `LimitedDemoEnvelope(max_positions=state["position_cap"])` |
| max 0.1% risk / trade | `risk_pct=state["risk_cap_pct"]` (0.001 in LIMITED_DEMO) |
| max 3 trades / day | `max_trades_per_day=3`, counter resets on date change |
| Guardian approval every order | `guardian_bridge.guardian_ok()` per trade; veto ⇒ break |
| strategy contract validation | `gate.authorize()` (contract, version, trial, symbol, stop) |
| broker-side stop mandatory | `req["sl"]` always set before `order_send` |
| ledger entry before submission | `PositionLedger.record_intent()` precedes the send |
| post-fill reconciliation | `_capture_execution()` → `broker_reconciliation.reconcile()` |
| automatic halt on critical failure | `record()` → `envelope.halt()` + loop `break` |
| demo account only | refuses unless `ACCOUNT_TRADE_MODE_DEMO` |

## Evidence recorded per execution
`broker_retcode · fill price (actual_entry) · requested price (expected_entry) · spread at fill
(pre/post) · estimated slippage · execution latency (ms) · stop verified · reconciliation result ·
duplicate check · volume match · guardian approved · defects`

Written to `registry/demo_execution_evidence.jsonl` and converted to **`DemoExecution` evidence →
OperationalBelief only**. Research influence remains bounded by the existing
`MAX_EXEC_RESEARCH_LOGODDS = 0.35` cap (untouched); `test_demo_updates_operational_not_research`
proves 40 clean demo trades move research ≤ 0.10 while operational rises > 0.40.

## Dashboard
`market_intel/web.py` now shows Research Belief and Operational Belief (with bars against their live
bars), current Promotion State and next state, **remaining requirements for FULL_DEMO and LIVE**,
daily/total demo trade count, position + risk caps, outstanding defects, evidence counts by class,
and Telegram configuration status.

## Regression tests — 11/11 (`test_phase702_1.py`)
cannot exceed daily trade cap · cannot pyramid beyond envelope · risk cap enforced by state ·
cannot execute below LIMITED_DEMO_APPROVED · SHADOW_APPROVED still cannot trade demo · cannot submit
without arming the guard · arming is single-use (one decision = one order) · critical reconciliation
failure halts · missing broker stop is critical · demo updates operational not research ·
live research bar unchanged.

Full suite: **72/72** across nine suites.

## Remaining gaps (unchanged from PHASE 702, not addressed here by design)
1. **Exit reconciliation — still outstanding.** `exit_verified` is recorded as `False`; positions are
   rebalance-managed and there is no exit-side reconciliation. This caps OperationalBelief, because
   one of the eleven quality checks can never pass today. **It must be built before FULL_DEMO is
   reachable in practice.**
2. Historical-reaction percentiles are recorded but do not yet score opportunity confidence.
3. Challenge Mode (conviction scaling / gated pyramiding) not started.
4. Unified audit index across the separate ledgers not built.

## Operating
```
py portfolio_mt5.py --config funded --demo-limited     # demo only, 1 position, 0.1%, 3/day
py -m market_intel.web --port 8787                     # belief + promotion dashboard
```
