# RELEASE_READINESS — release candidate `release/rc1`

Two questions, deliberately separated. Conflating them is how a working desk gets deployed on
the strength of a strategy nobody measured, and how a good strategy gets blamed for a broken desk.

---

## A. Is the DESK technically trustworthy enough for demo deployment?

**YES**, subject to the blockers below being accepted as non-blocking.

| Property | Evidence |
|---|---|
| A stale feed cannot fabricate a current clock | pinned VPS regression; 20,000-cycle soak, 0 violations |
| New orders unreachable outside `FEED_FRESH` | source ordering proof + soak invariant 1 |
| A stale instrument cannot produce a candidate | per-symbol gate inside pass 1, both directions proved |
| Losing the clock cannot stop an exit | `time_exits`/`reconcile` call no clock function and run first |
| Broker SL/TP never touched | no `TRADE_ACTION_SLTP` in the codebase |
| Caps enforced against candidates and real exposure | TASK-0004 suite intact after rebase |
| Corrupt/missing/expired/implausible state fails closed | four cases, all blocked |
| Only `+2/+3` can be trusted | `+4`, `−13`, `0` all rejected |
| Void evidence cannot reach posteriors or the CIO | `closed_trades()` drops void; `belief()` never passes `include_voided`; `allocate()` consumes beliefs, never the ledger |
| Healthy-feed parity | offset, eligibility, utility, legacy CIO path unchanged |

## B. Are the STRATEGIES profitable?

**UNKNOWN, and not addressed by this release.**

The ledger holds 17 rows. Six trades were voided for the clock defect. Two trading days are
recorded. No strategy on this desk has enough closed, valid, non-void evidence to separate its
expectancy from zero, and nothing in TASK-0004 or TASK-0005 was intended to change that.

This release makes the desk **measurable**. It does not make it **profitable**, and the
distinction is the point: until the desk records reality correctly, strategy results are not
evidence about strategies.

---

## Remaining BLOCKERS for demo deployment

None in the code. Two operational items must be settled by a human before the release runs live:

1. **Windows/NTP discipline is now a trading prerequisite.** `HOST_DRIFT_TOLERANCE_S = 300`
   and the only recorded drift samples are `−133s → −209s → −304s`. The worst sits marginally
   outside tolerance, so the desk will sometimes refuse entries with `HOST_CLOCK_UNTRUSTED`
   and the exact residual. That refusal is correct and was accepted deliberately; a
   fail-closed missed entry beats trading a wrong session.
2. **Deployment provenance.** The VPS is a git checkout of `phase404-live-demo` at
   `C:\Users\Administrator`, matching `42ad8b38` byte-for-byte. Deploying this candidate means
   moving that checkout to a branch containing it. Not done, not proposed here.

## Remaining IMPORTANT items — recorded, not fixed

| Item | Why it is not a blocker |
|---|---|
| `_start_logging` tees stdout only, so `sys.exit("HALT: …")` is invisible | Observability, not safety. Every refusal now also emits a structured `CLOCK_STATE` event |
| `ChallengeState.open_risk_pct` is ledger-only, no broker cross-check | The *group* cap is now broker-seeded; the *total* cap is not |
| `trading_days` counts shadow-only rows toward the FTMO four-day minimum | Correctness of a submission claim, not a loss path |
| Legacy stack shares the terminal and is invisible to every magic-990001 filter | All five tasks disabled since 2026-07-26; no 770001 position exists |
| A 1-hour backward feed jump is observationally identical to DST | Accepted residual; rate-limited to one change per hour, always with a blocked cycle |
| `.git-credentials` sits untracked inside the VPS working tree | One careless `git add -A` from exposure; the orchestrator never does that |
| 4 pre-existing test failures | Fail identically at base: two scratch files, one stale import, one missing CSV |

## What would change the answer to B

Not another feature. Closed, valid, non-void trades — enough of them, recorded by a desk whose
clock and allocation are now trustworthy. That is what the next phase is for.
