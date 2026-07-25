# PRODUCTION_READINESS — final review

Engineering review only. No code was written or modified for this document.

## Subsystem scores

| subsystem | score | justification |
|--|--|--|
| **Research maturity** | **7/10** | Genuinely rigorous: pre-registration, walk-forward, bootstrap CIs, a scorecard that has rejected far more than it approved, and honest negatives recorded rather than buried. One statistically significant finding (NFP continuation, t=+3.16/+3.44 over 114 releases). Loses points: the deployed portfolio's own pass-rate claim was overstated by my own methodology error (warmup contamination + vol-target selection bias); research lives in a separate repo with hand-exported artifacts. |
| **Execution maturity** | **6/10** | Fail-closed gate, one-shot arming, mandatory broker-side stops, ledger-before-submit, post-fill reconciliation — all real and tested. Loses points heavily: **zero live fills ever**, exit reconciliation absent, `exit_verified` permanently false. |
| **Operational maturity** | **4/10** | The four restart-safety defects are closed and the state model now matches the scheduled-one-shot reality. But nothing has been operated: no real restart observed, no real halt observed, no incident exercised. Runbooks are written, never rehearsed. |
| **Deployment maturity** | **5/10** | Improved from 3/10: SHA-pinned sync, manifest verification, banned-executor scan. Still: **the manifest is currently stale and omits the two critical new modules**, deployment is manual paste, and no runner refuses to start on `INCOMPLETE` (V-13 open). |
| **Monitoring maturity** | **5/10** | Two working dashboards, 16-subsystem healthcheck, live startup diagnostics, append-only audit log. But **alerting is not wired** — `telegram_notifier` has zero callers, so nothing pages a human. Silence carries no information. |
| **Recovery maturity** | **6/10** | Atomic + checksummed + backed-up state, fail-closed loading, human-only halt clearing, startup reconciliation. Loses points: recovery paths are mock-proven only; the ledger is still unlocked (V-06); belief store still non-atomic (V-05). |
| **Documentation maturity** | **8/10** | Extensive, current, and unusually honest — gaps and defects are documented as prominently as features. Loses points: volume now exceeds what one operator can hold, and several docs describe intent adjacent to implementation. |
| **OVERALL** | **5.9/10** | Code-complete and mock-verified. Not operationally verified. |

## Readiness statement
| axis | status |
|--|--|
| Code-complete | ✅ YES |
| Mock-verified | ✅ YES (98/98) |
| VPS-deployed | ❌ NO |
| Broker-connected | ❌ NO |
| Operationally verified | ❌ NO |

**Overall readiness: NOT READY.** Suitable for a *supervised evidence campaign* on a fresh demo
account after the deployment package is executed. Not suitable for unattended operation.

---

## "If this were your own trading platform, what would stop you from running it live tomorrow?"

**Eleven things. Any one of them alone would stop me.**

**1. It has never executed a single order.** Every safety guarantee in this system is proven against
mocks. The first real fill is an experiment. I would not put money behind a stop-loss mechanism whose
only evidence is that it works against a `SimpleNamespace`.

**2. The strategy's edge claim was wrong once already — and I made the error.** I reported a 48.8%
pass rate that was inflated by warmup contamination and by reporting the best of four vol sweeps. The
honest figure is mid-30s. A number I had to correct downward once is not a number I would size real
risk against.

**3. Exit reconciliation does not exist.** The system verifies entries meticulously and then stops
watching. `exit_verified` is hardcoded `False`. I have no mechanism proving a position closed as
intended, at the price intended, or at all.

**4. Nothing pages a human.** Telegram is implemented and wired to nothing. If the system halts at
02:00 on a Tuesday, it sits halted until someone happens to look. For unattended operation that is
disqualifying on its own.

**5. Contracts are unsigned (V-03).** Any process with disk access can write `LIVE_APPROVED` into a
JSON file and every belief, promotion and governance control is bypassed at the final step.

**6. I have been wrong repeatedly, confidently, in this codebase.** Attribution of the BTC trades
(three times). Cache-busting that did nothing. A TOCTOU race in my own safety fix that single-threaded
tests passed. The pattern is that my errors survive until something adversarial finds them — and live
trading is adversarial with money attached.

**7. Deployment integrity is not enforced at runtime.** The manifest is stale right now and omits
`safety_state.py` — the module that closes the critical defects. A VPS could pass `--verify` while
missing the fixes. Nothing blocks a runner from executing on a partial install.

**8. The belief store can still be corrupted (V-05).** Safety state got atomic writes; the belief
graph did not. A crash mid-write empties it, and an empty graph silently reads as `RESEARCH_ONLY` —
fail-closed by luck, with all accumulated evidence gone.

**9. The realistic edge does not justify the operational risk.** Diversified trend+carry is ~0.62
Sharpe, ~6%/yr at 8% vol. That is real and honest — and it is *not* enough return to justify running
an unproven autonomous system against real capital. The risk of an operational defect exceeds the
expected edge.

**10. Two belief systems still disagree (V-10).** `--live` reads v1, `--demo-limited` reads v2, and
`belief_feedback` writes v1 — which no runner consumes. Realised results currently feed nothing.

**11. No incident has ever been rehearsed.** The runbooks were written today and have never been
executed under pressure. An untested recovery procedure is a hypothesis.

### What would change my answer
Not more features. **Sixty days of boring, fully-evidenced demo operation** — 100 clean trades, 100%
stop verification, 100% reconciliation, zero unexplained executions, at least one real crash survived
correctly, and alerting that actually wakes someone up. Plus exit reconciliation built, contracts
signed, and the belief store made atomic.

**Then** the conversation about live capital is worth having. Not before.
