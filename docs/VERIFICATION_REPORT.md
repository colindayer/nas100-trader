# VERIFICATION_REPORT

**Role:** Principal Systems Verification Engineer. Adversarial audit, 2026-07-25.
**Method:** executable probes against a running installation, not source reading.
**No fixes were implemented.** Findings only.

**Headline: two CRITICAL defects defeat the LIMITED_DEMO safety envelope entirely.**
The envelope's daily trade cap and its automatic halt are both **in-memory only** and are erased by
the next process start. `run_demo_limited()` is designed to be invoked repeatedly.

---

## V-01 — Daily trade cap is defeated by process restart · **CRITICAL**

| | |
|--|--|
| **Severity** | CRITICAL — a governance control that does not hold |
| **Probability** | **Certain** if the runner is scheduled (the documented operating pattern) |
| **Consequence** | The "max 3 trades/day" envelope becomes unbounded. A 15-minute schedule permits **up to 96 trades/day** at 0.1% each ≈ **9.6% of account risk per day** — beyond the Guardian's 1% daily stop and any prop daily-loss rule |
| **Reproducibility** | 100% |

**Probe**
```
after 3 trades: allow=(False, 'DAILY_TRADE_LIMIT')
AFTER RESTART:  allow=(True,  'ok')          ← counter reset
```

**Root cause** `LimitedDemoEnvelope.__init__` sets `self._count = 0`; `run_demo_limited()`
constructs a new envelope on every invocation and never reads prior state
(probe 6: *loads prior state from disk: False*, *derives count from ledger: False*).

**Proposed fix** Derive `trades_today` from a persistent source rather than memory — count today's
entries in `registry/demo_execution_evidence.jsonl` (already append-only and already written per
trade) at envelope construction. Do **not** add a second state file.

---

## V-02 — Automatic halt does not survive restart · **CRITICAL**

| | |
|--|--|
| **Severity** | CRITICAL — the primary safety reaction is not durable |
| **Probability** | **Certain** once any critical failure occurs under a schedule |
| **Consequence** | A naked position or failed reconciliation halts the envelope; the next scheduled run starts clean and **trades again into the same fault**. The system's response to "something is badly wrong" lasts under 15 minutes |
| **Reproducibility** | 100% |

**Probe**
```
halted:        (False, 'HALTED: critical failure')
AFTER RESTART: (True,  'ok')                 ← halt erased
```

**Proposed fix** Persist a halt sentinel (e.g. `registry/HALTED.json` containing reason, timestamp,
offending trade id). Envelope construction must fail closed if it exists; clearing must require an
explicit human action. Surface it in `healthcheck.py` as a critical subsystem.

---

## V-03 — Strategy contracts are unsigned and trivially forgeable · **HIGH**

| | |
|--|--|
| **Severity** | HIGH — governance bypass |
| **Probability** | Low (needs disk access) but **impact is total** |
| **Consequence** | Editing one JSON field to `LIVE_APPROVED` grants real-money authorisation. Nothing detects, logs, or rejects it. All the belief/promotion machinery is bypassed at the last step |
| **Reproducibility** | 100% |

**Probe** `status: PAPER_APPROVED | signed or hashed: False`

**Proposed fix** Add a `content_hash` over the governance-critical fields plus an approval record;
`StrategyRegistry.load()` rejects a contract whose hash does not match. Pair with a `healthcheck`
assertion that no contract is `LIVE_APPROVED` while `promotion_pipeline_v2` says otherwise —
cross-checking two independent sources.

---

## V-04 — Guardian drawdown baselines reset every invocation · **HIGH**

| | |
|--|--|
| **Severity** | HIGH — the daily/total loss stops measure from the wrong origin |
| **Probability** | Certain on every scheduled run |
| **Consequence** | `guardian_check()` is called with no `day_start_equity` / `hwm`, so `guardian_bridge` defaults both to **current** balance/equity. After a loss the baseline moves down with the account, so realised drawdown always reads ≈ 0 and the daily stop **can never trigger** |
| **Reproducibility** | 100% (call site: `guardian_check(proposed_risk_pct=env.risk_pct)` — no baselines passed) |

**Proposed fix** Persist `day_start_equity` and `high_water_mark` (the guardian already has an atomic
state file) and pass them on every call. Until then the Guardian is effectively enforcing only
per-trade risk, not drawdown.

---

## V-05 — Belief store writes are non-atomic and unlocked · **HIGH**

| | |
|--|--|
| **Severity** | HIGH — corruption destroys governance state |
| **Probability** | Medium (power loss, or two processes writing) |
| **Consequence** | `BeliefGraphV2.save()` truncates and rewrites `registry/belief_v2.json`. A crash mid-write leaves an unparsable file. `BeliefGraphV2.load()` swallows the exception and returns an **empty graph** → promotion silently drops to `RESEARCH_ONLY`. Fail-closed by luck, but all accumulated operational evidence is **irrecoverably lost** |
| **Reproducibility** | Deterministic under induced crash |

**Probe** `atomic write (tmp+replace)? False · file lock? False`

**Proposed fix** Write to `.tmp` + `os.replace()` (the pattern already used in `downloader.py` and
`prop_risk_guardian.write_state_atomic`). Add a lock file for multi-process safety. Keep a rolling
backup so a corrupt store is detectable rather than silently empty.

---

## V-06 — Ledger appends are unlocked · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM |
| **Probability** | Low-medium (concurrent runners) |
| **Consequence** | Interleaved writes to `position_ledger.jsonl` can produce a torn line; `_load` parses with `json.loads` per line and would raise, and `PositionLedger()` is constructed inside the order path → an exception there **aborts submission** (fail-closed, but as an unhandled crash rather than a decision) |
| **Reproducibility** | Race-dependent |

**Proposed fix** Single-writer discipline (a lock file), and make `_load` skip malformed lines while
recording a defect rather than raising inside the order path.

---

## V-07 — Calendar serves unbounded stale data · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM — silent wrong-context |
| **Probability** | High (the feed rate-limits routinely; already observed) |
| **Consequence** | `_fetch_all()` returns `rows or []` with **no maximum age**. During an outage the dashboard and any consumer present week-old events as current, with no visual staleness indicator. Countdown timers would be nonsense |
| **Reproducibility** | 100% (block network, load) |

**Proposed fix** Cap stale service (e.g. 6h), and surface `cache_age` in the dashboard and
healthcheck. Never render an event as "upcoming" from a cache older than the event.

---

## V-08 — `healthcheck.py` mutates the state it observes · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM — observer effect |
| **Probability** | Certain |
| **Consequence** | The provider probe calls `cf.load()`, which **fetches and writes the calendar cache**. Running healthcheck consumes the feed's rate-limit budget and can cause the 429s it is meant to diagnose. A monitoring tool must not change system state |
| **Reproducibility** | 100% |

**Proposed fix** Add a read-only probe path (inspect cache age + config, no fetch), or make the
network probe opt-in (`--probe-network`). `--quick` already avoids it but is not the default.

---

## V-09 — Day boundary depends on unvalidated wall-clock · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM |
| **Probability** | Low (NTP correction, VPS migration, DST) |
| **Consequence** | `LimitedDemoEnvelope` compares `time.strftime("%Y-%m-%d")`. A backwards clock jump re-opens the daily quota; a forward jump closes it early. Also **local time, not broker/UTC time** — the "trading day" does not align with the broker's day or the prop firm's daily-loss window |
| **Reproducibility** | Deterministic under clock change |

**Proposed fix** Use UTC explicitly and align the boundary to the broker's daily reset. Compare
against the persisted ledger timestamps rather than a process-local date string.

---

## V-10 — Two parallel belief systems, silently divergent · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM — inconsistent evidence |
| **Probability** | Certain (both paths exist today) |
| **Consequence** | `--live` reads v1 (`belief_graph.json` via `belief_reader`); `--demo-limited` reads v2 (`belief_v2.json`). They can disagree about the same strategy. `belief_feedback.py` writes only v1 — which no current runner consumes, so **realised results feed nothing** |
| **Reproducibility** | 100% by inspection |

**Proposed fix** Retire v1 or make `belief_reader` a read-only adapter over v2. Point
`belief_feedback` at v2. Assert equality in healthcheck while both exist.

---

## V-11 — Silent-failure pattern persists in the calendar provider · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM |
| **Probability** | High |
| **Consequence** | Probe 7 found **2** `except → pass/continue` sites in `faireconomy_provider.py` (`_cache_read`, `_cache_write`). A read-only or full disk makes caching silently non-functional; the system then hammers the rate-limited feed and appears to "randomly" return 0 events. This exact pattern already cost multiple debugging cycles |
| **Reproducibility** | 100% (chmod the registry dir) |

**Proposed fix** Record failures in `LAST_ERROR` (the mechanism already exists) and surface disk
problems in healthcheck.

---

## V-12 — No shutdown path; in-flight order state is not durable · **HIGH**

| | |
|--|--|
| **Severity** | HIGH |
| **Probability** | Medium (VPS reboot, task kill, power) |
| **Consequence** | If the process dies between `record_intent()` and `order_send()`, the ledger holds an intent with **no broker position** (phantom). If it dies between fill and `_capture_execution()`, a **real position exists with no operational evidence and no reconciliation**. On restart nothing reconciles broker↔ledger; `classify_broker_positions` is never called by any runner |
| **Reproducibility** | Deterministic under induced kill |

**Proposed fix** A startup reconciliation pass: compare live broker positions (magic 880001) against
the ledger, classify orphans/phantoms, and **fail closed** until a human resolves them. The
primitives exist (`position_ledger.classify_broker_positions`) but are unwired.

---

## V-13 — Deployment drift is undetected at runtime · **MEDIUM**

| | |
|--|--|
| **Severity** | MEDIUM |
| **Probability** | High (demonstrated repeatedly this week) |
| **Consequence** | Runners do not verify the manifest before executing. A partially-synced VPS runs a mixture of versions — exactly the failure mode that produced hours of false debugging. `startup.py` reports deployment status but **nothing blocks on it** |
| **Reproducibility** | 100% |

**Proposed fix** `run_demo_limited()` should call `deploy.verify()` and refuse to execute on
`INCOMPLETE`. (`MODIFIED` should warn, since local edits are legitimate during development.)

---

## V-14 — Opportunity → execution path is not exercised · **LOW (latent)**

| | |
|--|--|
| **Severity** | LOW today, HIGH if enabled |
| **Probability** | n/a — currently inert |
| **Consequence** | `engine.evaluate_through_pipeline()` accepts `belief` and `guardian_ok` as **caller-supplied parameters**. Any future caller can pass `"ALLOW_PAPER", True` and bypass both. It fails closed only because no caller exists |
| **Reproducibility** | By inspection |

**Proposed fix** Have the function fetch belief and guardian itself rather than trusting arguments —
the same defect class as the now-fixed GAP 2.

---

## V-15 — `web.py` has no request limits or bind warning persistence · **LOW**

| | |
|--|--|
| **Severity** | LOW |
| **Probability** | Medium |
| **Consequence** | Public bind + token, but no rate limiting, no TLS, no access log. Token travels in the **query string** (logged by proxies, stored in browser history). Each page load triggers full MT5 + calendar work — a trivial request loop becomes a self-inflicted DoS on the trading VPS |
| **Reproducibility** | 100% |

**Proposed fix** Cache the rendered page (5–10s), add basic rate limiting, move the token to a
header or cookie, and log access attempts.

---

## Summary

| severity | count | ids |
|--|--|--|
| **CRITICAL** | 2 | V-01, V-02 |
| **HIGH** | 4 | V-03, V-04, V-05, V-12 |
| **MEDIUM** | 7 | V-06 … V-11, V-13 |
| **LOW** | 2 | V-14, V-15 |

### What held up under attack
- Execution gate correctly blocks unknown strategies and unarmed submissions.
- Promotion falls back to `RESEARCH_ONLY` with a missing belief store (probe 10 ✅).
- Arming is genuinely single-use and thread-isolated (probe 3 ✅).
- Reconciliation flags naked positions as CRITICAL.
- No fail-open `except → pass` in the execution path itself (probe 7: 0 in `portfolio_mt5.py`,
  `demo_evidence.py`, `engine.py`).

### The pattern behind the worst defects
**V-01, V-02, V-04 and V-12 share one root cause: safety state lives in memory, in a process designed
to be started repeatedly.** Every control that must span invocations — daily counts, halts, drawdown
baselines, in-flight orders — is lost at exit. The architecture assumes a long-running supervisor;
the deployment model is a scheduled one-shot. **That mismatch, not any individual bug, is the
platform's most serious weakness.**

### Verdict
The earlier maturity rating of **LIMITED DEMO READY** does not survive this audit.
With V-01 and V-02 open, the limited-demo envelope is **not enforceable across restarts**.

**Recommended status: NOT READY FOR DEMO EXECUTION until V-01, V-02, V-04 and V-12 are closed.**
