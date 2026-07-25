# OPERATIONAL_VALIDATION_PLAN

**Objective:** prove this platform can operate unattended for **60 consecutive days without a single
unexplained operational incident.**

The thesis: an auditable, resilient platform whose behaviour is understood is worth more than a bot
that happened to make money for a week. Only once the operational layer is proven can the research
question — *does the edge exist?* — be answered without the operational layer obscuring the result.

**P&L is not a metric anywhere in this plan.**

---

## PHASE A — DEPLOY (target: 1 session)

Pinned build: **`aebf87640f6f8e5bf26921f33288d71d8ad13ded`** · 36 tracked files · 112/112 tests.

### A.1 Pre-deployment (VPS, before syncing anything)
```powershell
# 1. Stop everything
#    MT5: click Algo Trading -> grey
Get-ScheduledTask | Where-Object {$_.TaskName -like "*MarketIntel*" -or $_.TaskName -like "*Recorder*"} | Disable-ScheduledTask
Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. EXPORT MT5 HISTORY FIRST — irreplaceable, and the trade count is currently UNKNOWN
#    MT5 -> Toolbox -> Journal  -> right-click -> Save As
#    MT5 -> Toolbox -> Experts  -> right-click -> Save As
#    MT5 -> Reports -> export    ; copy MQL5\Logs\ off the VPS

# 3. Archive existing evidence (never delete)
Compress-Archive -Path registry\* -DestinationPath "registry_archive_$(Get-Date -f yyyyMMdd).zip" -Force
```

### A.2 Sync (`py deploy.py --sync-script` on the Mac emits this block)
SHA-pinned URLs only. `?v=` cache-busters do **not** work on raw.githubusercontent.

### A.3 Verification gate — every line must pass, in order
| # | command | required result |
|--|--|--|
| 1 | `py deploy.py --verify` | **COMPLETE**, 36/36 files |
| 2 | `py deploy.py --scan-executors` | **CLEAN** — no `live_trader.py` on disk, in scripts, in scheduled tasks, or running |
| 3 | `py healthcheck.py` | **0 critical failures** |
| 4 | `py startup.py` | version = `aebf876…`, deployment COMPLETE, DEMO account |
| 5 | calendar | `faireconomy: ~70 events, ~50 forecasts` |
| 6 | guardian | `ALLOW`, or `BLOCK (GUARDIAN_SNAPSHOT_BAD)` — **never** `GUARDIAN_UNAVAILABLE` |
| 7 | belief | research ≈ 0.61, operational ≈ 0.25 |
| 8 | promotion | `LIMITED_DEMO_APPROVED`, caps `1pos / 0.10%` |
| 9 | contracts | `portfolio_multisleeve` demo-eligible, **signature valid**, `rejected: []` |
| 10 | Telegram | configured — **and understood to emit nothing yet** |
| 11 | market intelligence | dashboard renders regime, kill zones, structure, countdown |

**Known caveats to expect (not failures):**
- `startup.py` may show *manifest commit ≠ local commit* — the manifest records the commit it was
  built at, and committing it changes HEAD. **File hashes are what `--verify` enforces.**
- `portfolio_mt5.py` syncs to `scripts\`. Run `py scripts\portfolio_mt5.py`, or copy it to the root.
- `deploy.py --scan-executors` will report `SCHEDULER_NOT_CHECKED` if `schtasks` is unavailable —
  verify Task Scheduler manually in that case.

**Exit criteria:** all 11 rows pass. **Do not open a new demo account until they do.**

---

## PHASE B — SHADOW MODE (target: 30 days, zero orders)

Scheduled runs of shadow-only components. **`--demo-limited` is NOT enabled in this phase.**

| task | cadence |
|--|--|
| `py scripts\portfolio_mt5.py --config funded` | 4×/day (session opens) |
| `py -m market_intel.reaction_recorder --symbols EURUSD,XAUUSD,NAS100` | every 15 min |
| `py -m market_intel.web --host 0.0.0.0 --port 8787 --token <secret>` | at boot, always up |
| `py healthcheck.py >> registry\healthcheck_history.log` | daily 06:00 UTC |
| `py deploy.py --verify >> registry\deploy_history.log` | daily 06:00 UTC |

### Deliberate fault injection (this is the point of Phase B)
| week | injected fault | expected behaviour |
|--|--|--|
| 1 | reboot the VPS mid-session | state survives; startup reconciles; no surprise |
| 2 | kill MT5 while a run is scheduled | reconciliation fails → **halt**; no trading |
| 2 | `safety_state.halt('drill')` then reboot | still halted after reboot; requires named clear |
| 3 | disconnect network for 1h | calendar degrades to cache; no crash; recovery logged |
| 3 | corrupt `safety_state.json` deliberately | `.bak` recovery **or** fail-closed halt |
| 4 | run two schedulers simultaneously | lock refuses the second writer; no double-count |
| 4 | deploy a deliberately incomplete file set | `--verify` = INCOMPLETE and is noticed |

**Exit criteria:** 30 consecutive days · 0 unexplained events · every injected fault behaved as
predicted · every restart preserved state · ≥1 real (uninjected) restart survived.

---

## PHASE C — LIMITED DEMO (target: 30 days, ≤3 trades/day)

Only if Phase B is clean. New demo account, flat, documented starting balance.

Fixed for the whole phase: **1 position · 0.1–0.25% risk · 3 trades/day · manual review of every
fill · complete evidence package per trade.** No configuration changes mid-phase.

**First five fills are reviewed one at a time before the next is permitted.**

Per-fill review checklist:
`broker-side SL present · volume matches intent · magic 880001 · comment correct · ledger entry
created BEFORE submission · reconciliation passed · slippage recorded · latency recorded · retcode`

**Kill criteria (end Phase C immediately):** any orphan position · any naked fill · any duplicate
execution · any unexplained execution · any state corruption not auto-recovered · a halt that fails
to persist · any governance bypass.

---

## PHASE D — MACRO INTELLIGENCE (research only, no execution changes)

Only after C. Treated as **research projects that feed the existing architecture, not replace it**
(per `QUANT_OS_ARCHITECTURE.md`):
1. Macro Board — **extend** `regime.py`; every claim carries evidence + contradictions + unknowns.
2. Evidence Panel — independent channels only; **no voting**; disagreement recorded.
3. Futures / cross-asset — **one pre-registered study**; adopt only on a pass. Current prior is weak
   (PHASE 520: 1 robust hit at +0.023 AUC; PHASE 510: HTF context AUC ≈ 0.50).

None of these may emit a signal. All enter the Trial Registry.

---

## THE 60-DAY SCORECARD

Measured across Phase B (30d shadow) + Phase C (30d limited demo).

| metric | target | measurement source | how a breach is detected |
|--|--|--|--|
| Unexplained executions | **0** | broker deals ↔ `position_ledger` | any deal with no ledger intent |
| Missing broker-side stops | **0** | `broker_reconciliation` per fill | `NAKED_POSITION` finding |
| Reconciliation failures | **0** | `startup_reconciler` every start | any CRITICAL finding |
| Guardian bypasses | **0** | audit log ↔ order intents | an intent with no guardian approval |
| Deployment drift | **0** | `deploy.py --verify` daily | any non-COMPLETE verdict |
| Critical healthcheck failures | **0** | `healthcheck.py` daily | any `FAIL` on a `*` subsystem |
| Startup failures | **0** | `safety_state_audit.jsonl` | any start not reaching SLEEP |
| Evidence captured per trade | **100%** | `demo_execution_evidence.jsonl` | any record with a null field |
| Manual interventions | **tracked + explained** | `registry/manual_actions.log` | any action with no written reason |

**Every metric is conjunctive.** One breach in 60 days resets the clock — the claim is
*"without a single unexplained incident"*, not *"mostly clean"*.

### Weekly evidence pack (automatic, reviewed by a human)
healthcheck history · deployment verdicts · startup/shutdown log · reconciliation results ·
provider availability · halts and their clears · manual interventions · trade evidence completeness.

### Honest note on "unattended"
**The platform is not yet capable of true unattended operation.** `telegram_notifier` has zero
callers: a halt at 02:00 sits unnoticed until someone looks. Until alerting is wired,
"unattended for 60 days" means *"ran without human input and was reviewed daily"* — not
*"could be left alone safely"*. **Wiring alerting is the highest-value remaining work** and should
precede Phase C.

---

## WHAT SUCCESS ACTUALLY BUYS

Not profit. It buys the ability to answer the research question cleanly.

Right now, if the strategy loses money, there are two indistinguishable explanations: the edge is
absent, or the operational layer corrupted the result. **The previous demo account lost 4.9% and
could not distinguish between them** — that is why it produced almost no usable evidence.

After 60 clean days, a loss means the edge is absent. That is the entire point.
