# DEMO_ACCOUNT_POSTMORTEM — Pepperstone-Demo 61552095

Formal postmortem. No decision is defended; no loss is justified.
Every figure is sourced from broker output or repository evidence. Where evidence is absent, the
finding is marked **UNKNOWN** rather than inferred.

---

## 1. EXECUTIVE SUMMARY

| metric | value | source |
|--|--|--|
| Account | 61552095, Pepperstone-Demo (Hedge) | MT5 title bar |
| Lifetime observed | ~2026-07-10 → 2026-07-25 (~2 weeks under observation) | MT5 history + session record |
| Starting balance | **50,000.00 USD** | MT5 Reports: Deposit 50 000 |
| Ending balance | **48,436.96 USD** | MT5 Trade tab |
| Ending equity | **≈ 47,558 – 47,633 USD** (float varied intraday) | MT5 Trade tab |
| Net closed P&L | **−1,663.39 USD** | MT5 Reports: Total |
| Gross profit / loss | +600.52 / **−2,163.56** | MT5 Reports |
| Swaps | −99.75 | MT5 Reports |
| Peak floating loss | ≈ −878 (3 open BTC positions) | MT5 Trade tab |
| **Total drawdown from deposit** | **≈ −4.9 %** (50,000 → ~47,558) | derived |
| MT5-reported Max Drawdown | 1.99 % | MT5 Reports (measures balance-curve DD, not deposit-to-equity) |
| Sharpe (MT5) | **−0.4** | MT5 Reports |
| Profit Factor | **0.28** | MT5 Reports |
| Max deposit load | 4.31 % | MT5 Reports |
| Strategies live | S1–S5 (QQQ/GLD/GDX/SLV/USO), **BTC sweep**, **BTCTREND**, XSMOM, OVN — via `live_trader.py`, magic **770001** | `live_trader.py` + `mt5_broker.py:212` |
| Trade count | **UNKNOWN — not captured before the account was disturbed** | — |
| Monthly performance | July 2026 month-to-date **−4.8 %**, breaching the −4 % monthly limit | Telegram `MONTHLY KILL SWITCH` alerts |

**Bottom line:** the account lost ~4.9 % of deposit with a profit factor of 0.28 and a negative
Sharpe. The monthly kill switch is currently latched and repeating hourly.
**No trade on this account was ever placed by any component built during the PHASE 601/700/701/702
work.** All execution came from the pre-existing `live_trader.py` stack.

---

## 2. TIMELINE

| when | event | evidence |
|--|--|--|
| pre-July | `live_trader.py` + `mt5_broker.py` (magic 770001) deployed to VPS, AutoTrading on | repo history; MT5 Journal |
| 2026-07-20 18:39 | BTCUSD buy 0.30 @ 64,836.80, SL 52,964 (**~18 % stop**) | MT5 Trade tab |
| 2026-07-21 11:48 | BTCUSD buy 0.06 @ 66,220.36, SL 52,943 | MT5 Trade tab |
| 2026-07-23 11:48 | BTCUSD buy 0.22 @ 65,621.47, SL 52,485 | MT5 Trade tab |
| ~2026-07-23 | Prop Risk Guardian written (`scripts/prop_risk_guardian.py`), **monitor-only, never enforcing** | repo |
| 2026-07-24 | Replay showed the Guardian *would have* cut −545 → −0.30 on historical fills | `RISK_GUARDIAN_REPLAY.md` |
| 2026-07-24 | I asserted three times that the BTC positions were not from our code | session record |
| 2026-07-24 | **Attribution corrected**: MT5 tooltip "Expert id 770001" = `mt5_broker.py:212`. **It was our code.** | MT5 Journal + source |
| 2026-07-24 | PHASE 601 recovery: contracts, fail-closed gate, execution guard retiring the legacy path | repo |
| 2026-07-24 | `ORDER_LIFECYCLE.md` audit found `order_send` transmitted **no stop-loss** in the portfolio path | audit |
| 2026-07-24 | Deployment defect found: `raw.githubusercontent.com` ignores `?v=` → VPS ran stale files for hours | session record |
| 2026-07-24 | PHASE 702: Research/Operational belief split; execution-evidence leak found and capped | repo |
| 2026-07-24–25 | Market Intelligence, calendar chain, dashboards, Telegram module, reaction recorder added | repo |
| 2026-07-25 | SSL `CERTIFICATE_VERIFY_FAILED` on VPS traced to Windows cert store | session record |
| 2026-07-25 | Adversarial audit: **V-01/V-02 CRITICAL** — demo envelope caps and halt do not survive restart | `VERIFICATION_REPORT.md` |
| 2026-07-25 08:48→13:48 | `MONTHLY KILL SWITCH: −4.8 % exceeds −4 %` repeating **hourly** | Telegram |
| ongoing | `BROKER INIT FAIL alpaca: credentials missing` | Telegram |

---

## 3. ROOT CAUSE ANALYSIS

### Loss 1 — BTC positions (≈ −800 floating, largest single exposure)
**Primary cause: RISK MANAGEMENT.** Evidence:
- Stops at ~52,500 against entries ~65,000 = **~19 % stop distance**. `live_trader.py:130` sets
  `STOP_BTC = 0.025` (2.5 %). The deployed stop does **not** match any configured value.
  → the stop actually used is **UNKNOWN**; it matches neither `run_btc` nor a 2.5 % floor.
- Three separate BTC longs accumulated into one directional exposure. No concurrent-position or
  correlated-exposure limit existed on the live path.
- No take-profit on any leg.

**Contributing: RESEARCH FAILURE.** The BTC sweep belongs to the liquidity-sweep family, which
independent tests later scored at posterior ≈ 0.05 (six rejections). It should not have been live.

### Loss 2 — Aggregate −1,663 closed P&L, PF 0.28
**Primary cause: RESEARCH FAILURE.** Evidence: gross profit 600 vs gross loss 2,164 across S1–S5 /
BTC / XSMOM / OVN. None of these strategies had a passing pre-registered trial; the contract audit
later assigned every one of them `RESEARCH_ONLY`, `SUSPENDED` or `NEEDS_REPLICATION`.

### Loss 3 — Guardian did not prevent any of it
**Primary cause: MISSING FEATURE (never wired).** Evidence: the Guardian was built as a *monitor*
and never gated `live_trader.py`. Independently, `VERIFICATION_REPORT` V-04 shows the Guardian's
drawdown baselines default to *current* equity, so its daily stop could not have fired even if wired.

### Attribution delay
**Primary cause: HUMAN ERROR (mine).** Evidence: I claimed three times the positions were external.
The disproof — magic 770001 in `mt5_broker.py:212` — was available in the repository the entire time.
**Consequence: ~1 day of the incident spent misattributing rather than stopping the bleed.**

### `BROKER INIT FAIL alpaca`
**CONFIGURATION ERROR.** `live_trader.py` defaults to the Alpaca broker; credentials absent on the
VPS. Non-fatal but indicates the runner is still being launched with an unintended configuration.

### What is NOT the cause
- **Not deployment error.** Stale-file incidents cost debugging time but placed no trades.
- **Not the new architecture.** PHASE 601/700/701/702 components have never submitted an order.

---

## 4. LESSONS LEARNED

**L1 — Live code ran without a governing contract.**
*What:* eight strategies traded real (demo) capital with no approval record.
*Why:* execution predated governance; nothing required authorisation.
*Prevention:* `gate.authorize()` now blocks on missing contract/trial/version; `execution_guard`
retires the legacy `place_order` path (`test_legacy_retired` 3/3).

**L2 — I defended a conclusion instead of checking it.**
*What:* asserted three times that BTC trades were external; they were ours.
*Why:* I reasoned from expectation (stop distance didn't match config) rather than from broker
metadata that was one grep away.
*Prevention:* attribution must start from broker metadata (magic/comment/Journal) before any claim.
Encoded in `ORDER_LIFECYCLE.md` and `orphan_policy`.

**L3 — Orders could be submitted without a broker-side stop.**
*What:* the portfolio path's `order_send` carried no `sl`.
*Why:* the gate validated a stop that the executor never transmitted — validation and transmission
were separate and untested together.
*Prevention:* mandatory `sl` clamped to `trade_stops_level`, plus post-fill reconciliation that halts
on `MISSING_BROKER_STOP`.

**L4 — Silent exception handling hid every failure.**
*What:* `except Exception: return []` made an SSL failure, a rate-limit and a missing file
indistinguishable from "no data" — costing multiple debugging cycles.
*Why:* defensive coding applied without an error channel.
*Prevention:* `LAST_ERROR` + `diagnose()` in the calendar provider; `healthcheck.py` reports every
subsystem explicitly. **Still present in 2 sites (V-11).**

**L5 — Deployment had no integrity check.**
*What:* `?v=` cache-busters do nothing on `raw.githubusercontent.com`; the VPS silently ran old code
while we debugged the new code.
*Why:* assumed cache-busting worked; no version check existed on the VPS.
*Prevention:* SHA-pinned URLs, `MANIFEST.json`, `deploy.py --verify`. **Not yet enforced at
runtime (V-13).**

**L6 — Dashboards printed hardcoded status.**
*What:* the text dashboard printed "GUARDIAN: not wired / BELIEF GRAPH: not wired" as a literal
string *after* both were wired.
*Why:* a status line written before the feature and never revisited.
*Prevention:* `startup.py` computes every field at call time; repo-wide stale-string audit.

**L7 — Safety state was never persisted.**
*What:* daily trade caps, halts and drawdown baselines live in memory in a process designed to be
restarted every 15 minutes.
*Why:* the architecture assumes a long-running supervisor; the deployment is a scheduled one-shot.
*Prevention:* **NOT YET FIXED.** This is V-01/V-02/V-04/V-12 and is the single most dangerous
finding in the audit.

**L8 — Research conclusions did not reach production.**
*What:* the sweep family was rejected six times in research while a sweep strategy traded live.
*Why:* the firewall stopped research reaching production — including its *negative* findings.
*Prevention:* Belief Graph + promotion pipeline now gate execution on posterior.

---

## 5. ARCHITECTURE IMPROVEMENTS ALREADY MADE

| improvement | failure it prevents |
|--|--|
| `gate.authorize()` fail-closed chain | L1 — trading without contract/trial/version/symbol/stop |
| `execution_guard` one-shot arming | unauthorised or duplicated submission; retires legacy path |
| Mandatory broker-side SL + post-fill reconcile | L3 — naked positions (the BTC failure mode) |
| Stop-distance plausibility check (>15 % rejected) | **the exact ~19 % BTC stop would now be blocked** |
| Position/pyramiding caps from promotion state | three-BTC-longs accumulation |
| Belief Graph v2 + 5-state promotion | L8 — running research-rejected strategies |
| Execution→research log-odds cap (0.35) | good execution buying edge-confidence |
| `position_ledger` + orphan policy | unattributed positions (L2) |
| `deploy.py` manifest + SHA-pinned sync | L5 — stale-version drift |
| `healthcheck.py` (16 subsystems) + `startup.py` | L4, L6 — silent failure, stale status |
| Contract statuses set conservatively | every legacy strategy now blocked by default |

**Verified:** replaying the three real BTC trades through the current gate → **3/3 BLOCKED**.

---

## 6. REMAINING RISKS (ranked)

| # | risk | severity | why it can cause another incident |
|--|--|--|--|
| 1 | **V-01/V-02** envelope caps + halt lost on restart | **CRITICAL** | 3-trades/day becomes ~96/day; a halt lasts <15 min |
| 2 | **V-04** Guardian drawdown baselines reset each call | **HIGH** | daily/total loss stops cannot trigger |
| 3 | **V-12** no startup reconciliation | **HIGH** | phantom intents / live positions with no evidence after a crash |
| 4 | **V-03** contracts unsigned | **HIGH** | one JSON edit grants `LIVE_APPROVED` |
| 5 | **V-05** belief store non-atomic | HIGH | corruption silently empties governance state |
| 6 | **legacy `live_trader.py` still installed on the VPS** | **HIGH** | it caused this incident and is still present; only the `place_order` guard stops it |
| 7 | V-13 no runtime deployment check | MEDIUM | mixed-version execution |
| 8 | V-07/V-11 stale calendar, silent cache failure | MEDIUM | wrong macro context |
| 9 | Zero live fills ever validated | HIGH | every safety proof is mock-based |

---

## 7. READINESS ASSESSMENT

### Should a new demo account be opened? **YES — but not on Monday.**

**Why a new account is justified:** the current one is *confounded*. It contains positions from an
unapproved legacy system, a latched monthly kill switch, unknown historical trade attribution, and a
balance that no longer reflects a clean starting point. As an experiment it is uncontrolled — any
future measurement on it would be uninterpretable. **Fresh account = clean baseline. That is
experimental hygiene, not a fresh start to hide a loss.**

**Why not Monday:** V-01 and V-02 mean the demo envelope is unenforceable across restarts. Opening a
new account and running `--demo-limited` on a schedule would reproduce the same class of incident
with a different strategy.

### Required checklist before the first trade on the new account
1. **V-01, V-02, V-04, V-12 closed and tested** (persisted trade count, persisted halt, real
   drawdown baselines, startup reconciliation).
2. **`live_trader.py` removed from the VPS** — not merely guarded. It caused this incident.
3. Any residual positions closed; account flat; kill switch cleared.
4. `py deploy.py --verify` → **COMPLETE**.
5. `py healthcheck.py` → **0 critical failures**.
6. `py startup.py` shows the expected account, DEMO mode, promotion state, guardian ALLOW.
7. Exactly **one** strategy eligible; `--demo-limited` only; 1 position, 0.1 %, 3/day.
8. First five fills **manually reviewed**: broker-side SL present, volume correct, magic/comment
   correct, ledger entry exists, reconciliation passed.

---

## 8. SUCCESS CRITERIA FOR THE NEXT DEMO

**Success is measured in evidence quality, not P&L.**

| dimension | criterion |
|--|--|
| Operational reliability | ≥ 30 consecutive scheduled runs with no unhandled exception; halt survives restart (proven by induced restart) |
| Execution correctness | 100 % of fills carry a broker-side SL; 100 % ledgered; 100 % reconciled; **0 orphans**; 0 duplicates across a forced restart |
| Governance compliance | 0 orders without a promotion-state authorisation; contract statuses unchanged except through the documented promotion path |
| Drawdown | account drawdown < 3 % over the evaluation; **no single day > 1 %** |
| Healthcheck | 0 critical failures on every scheduled run; recorded to a log |
| Deployment | `deploy.py --verify` = COMPLETE at every startup; any INCOMPLETE blocks execution |
| Evidence yield | ≥ 30 `DemoExecution` records with complete slippage/spread/latency fields |

**The next demo is a success if it produces 30 clean, fully-evidenced trades — even at a loss.**
It is a failure if it makes money with unverified stops or unattributed positions.

---

## 9. ACTION ITEMS

### Immediate (before Monday)
1. **Do not start a new demo account yet.**
2. Disable AutoTrading; stop `live_trader.py`; disable any scheduled task that relaunches it.
3. Manually close the 3 BTC positions on the old account; record final numbers.
4. Export MT5 history (Journal + Experts + Reports) — the trade count is currently **UNKNOWN** and
   will be unrecoverable once the account is abandoned.
5. Remove `live_trader.py` and `mt5_broker.py` legacy entry points from the VPS.

### Short term (this week, before any new account)
6. Fix V-01 (persist daily count from the evidence ledger).
7. Fix V-02 (halt sentinel file; clearing requires human action).
8. Fix V-04 (persist and pass guardian day-start equity + HWM).
9. Fix V-12 (startup reconciliation broker ↔ ledger; fail closed on mismatch).
10. Enforce V-13 (runner refuses to execute on `INCOMPLETE` deployment).

### Long term
11. Sign strategy contracts (V-03).
12. Atomic belief writes + lock (V-05).
13. Wire Telegram to real events (currently zero callers) — this incident's kill-switch alerts came
    from the *legacy* system, not the new notifier.
14. Retire belief v1 (V-10).
15. Bound stale calendar service (V-07).

---

## 10. FINAL RECOMMENDATION

**Treat the next demo account as expensive engineering evidence, not as a trading attempt.**

The old account produced almost no usable evidence despite losing ~4.9 %: no reliable trade count, no
per-trade execution records, no spread/slippage/latency capture, no reconciliation, and until late no
correct attribution. **It cost a loss and returned almost nothing measurable.** That is the real
failure — not the drawdown.

To maximise learning per trade on the next account:
1. **One strategy, one symbol, one position.** Confounded accounts cannot be analysed — that is
   precisely why this one must be retired.
2. **Record execution facts, not opinions.** Expected vs actual entry, spread at fill, slippage,
   latency, retcode, stop verified, reconciliation result — `TradeExecutionRecord` already defines
   all of it; it has simply never run.
3. **P&L is not the metric.** OperationalBelief rises on execution *correctness* and deliberately
   ignores profit. Thirty clean losing trades are more valuable than thirty unverified winners.
4. **Stop on the first defect.** A halt that survives restart is the difference between one bad trade
   and ninety-six.
5. **Never let a strategy trade because it exists.** Every strategy in this incident traded because
   it was installed, not because it was approved.

**Recommended sequence:** close and archive the old account → fix V-01/02/04/12 → open the new
account → run 30 evidence-gathering trades under the limited envelope → only then discuss whether the
strategy is worth anything.
