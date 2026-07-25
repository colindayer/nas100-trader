# STAGE 4 VERIFICATION — critical defect closure

Adversarial verification of the V-01/V-02/V-04/V-12 implementation.
**Tests passing does not mean demo-ready.** Readiness is stated on five separate axes below.

## Defect → evidence mapping

| defect | requirement | test | result |
|--|--|--|--|
| **V-01** | 3 trades then restart blocks the 4th | `test_v01_restart_after_3_trades_blocks_the_4th` | ✅ |
| V-01 | counter resets only on UTC day rollover | `test_v01_counter_resets_only_on_utc_day_rollover` | ✅ |
| V-01 | two processes cannot overspend | `test_two_processes_cannot_overspend_envelope` | ✅ |
| V-01 | duplicate intent not double-counted | `test_record_trade_is_idempotent` | ✅ |
| **V-02** | halt survives restart | `test_v02_restart_after_halt_remains_halted` | ✅ |
| V-02 | halt survives day rollover | `test_v02_halt_survives_day_rollover` | ✅ |
| V-02 | clearing requires a named actor | `test_v02_halt_requires_explicit_human_clear` | ✅ |
| **V-04** | day-start equity survives restart | `test_v04_drawdown_baseline_survives_restart` | ✅ |
| V-04 | high-water mark ratchets up only | `test_v04_hwm_ratchets_up_only` | ✅ |
| **V-12** | clean reconciliation passes | `test_v12_clean_reconciliation_passes` | ✅ |
| V-12 | orphan broker position detected + halts | `test_v12_detects_orphan_position_and_halts` | ✅ |
| V-12 | orphan intent detected | `test_v12_detects_orphan_intent` | ✅ |
| V-12 | fill without ledger evidence detected | `test_v12_detects_fill_without_ledger_evidence` | ✅ |
| V-12 | missing fill detected | `test_v12_detects_missing_fill` | ✅ |
| V-12 | unverified broker-side stop detected | `test_v12_detects_naked_position` | ✅ |
| V-12 | foreign position reported, does not halt | `test_v12_detects_foreign_position_without_halting` | ✅ |
| V-12 | broker unavailable blocks trading | `test_v12_broker_unavailable_blocks_when_required` | ✅ |
| V-12 | reconciliation failure blocks execution | `test_v12_reconciliation_failure_blocks_execution_path` | ✅ |
| persistence | corrupt state fails closed | `test_corrupt_state_fails_closed` | ✅ |
| persistence | tampered checksum fails closed | `test_checksum_tamper_fails_closed` | ✅ |
| persistence | wrong schema fails closed | `test_schema_version_mismatch_fails_closed` | ✅ |
| persistence | missing state → safe bootstrap | `test_missing_state_documented_safe_bootstrap` | ✅ |
| persistence | backup recovers unreadable primary | `test_backup_recovers_unreadable_primary` | ✅ |
| persistence | lock refuses concurrent writer | `test_lock_prevents_concurrent_writer` | ✅ |
| audit | every transition logged | `test_every_transition_is_audited` | ✅ |

**26/26 new regressions · 98/98 total suite.**

## Defects found *during* this implementation (adversarial pass)

1. **TOCTOU race — REAL, fixed.** `allow()`-then-`record_trade()` is not atomic: under 4 concurrent
   threads the envelope recorded **6 trades against a cap of 3**. Fixed by moving cap enforcement
   *inside* the lock as a compare-and-increment (`record_trade(max_per_day=…)` raising
   `EnvelopeExhausted`). Proven by `test_two_processes_cannot_overspend_envelope`.
2. **`audit()` path frozen at import** — the module default bound `AUDIT_PATH` at definition time, so
   it could not be redirected. Fixed to resolve at call time.
3. **Older suites shared the production state file** — a halt correctly persisted across tests, which
   is V-02 working as designed. Fixed with per-test temp paths, not by weakening persistence.

## Residual weaknesses (NOT fixed, stated honestly)

| id | issue | why it still matters |
|--|--|--|
| R-1 | Lock is advisory and single-host | protects concurrent local processes; not two VPSs on one account |
| R-2 | `EnvelopeExhausted` after a fill halts, but the fill already happened | state/reality divergence is contained, not prevented |
| R-3 | Reconciliation trusts MT5's reported `sl` | a broker-side stop reported but not honoured is undetectable here |
| R-4 | Ledger writes still unlocked (V-06 open) | torn line under concurrent writers |
| R-5 | Contracts still unsigned (V-03 open) | disk edit still grants LIVE_APPROVED |
| R-6 | Belief store still non-atomic (V-05 open) | only safety state got atomic writes in this scope |

## Readiness — five separate statements

| axis | status | basis |
|--|--|--|
| **Code-complete** | ✅ **YES** for V-01/02/04/12 | all four implemented within approved scope |
| **Mock-verified** | ✅ **YES** | 98/98 tests, all against mocks/temp state |
| **VPS-deployed** | ❌ **NO** | not synced; VPS still lacks `deploy.py`/`healthcheck.py` |
| **Broker-connected** | ❌ **NO** | no MT5 on this machine; zero live reconciliations run |
| **Operationally verified** | ❌ **NO** | zero fills, zero real restarts, zero real halts observed |

**The system is NOT demo-ready.** It is code-complete and mock-verified only.

## Blocking items before demo execution
1. Sync to VPS; `deploy.py --verify` = COMPLETE.
2. `deploy.py --scan-executors` = CLEAN **on the VPS** (must show no `live_trader.py` in scripts,
   scheduled tasks, or running processes).
3. Export MT5 account history for 61552095 **before** any cleanup.
4. Manually close the 3 BTC positions per the checklist — **no automatic closing**.
5. Observe one real restart mid-session and confirm the counter and any halt persist.
