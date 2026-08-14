# ARCHITECTURE — FTMO Demo Trading Desk

_Generated 2026-08-14 from repository inspection, not from memory._

## 0. Findings that changed the design

Three facts discovered during inventory contradict the assumed architecture.

**1. `data/` is gitignored.** Line 8 of `.gitignore`. Every ledger, brain event, telemetry
snapshot and log is therefore invisible to Git. The "VPS pushes evidence, Mac pulls it" design
cannot work until this is deliberately changed — see `HUMAN_ACTION_REQUIRED.md`.

**2. The repository is 1.26 GiB**, dominated by a tracked 1.2 GB `quantitative-trading-free-lesson`
directory. This is why pushes intermittently return HTTP 500. Any automation that pushes on a
schedule will inherit that fragility.

**3. 10 modules are live; ~140 are legacy.** They share one flat directory. This has already
caused one real failure (`broker.py` shadowed by the `broker/` package, breaking
`test_fill_ledger.py`). Legacy scripts are not dead weight — they are a live import hazard.

## 1. Live components

| Module | Purpose | Source of truth for | Frequency | Failure mode | Recovery |
|---|---|---|---|---|---|
| `challenge_controller.py` | Trading. Preflight, CIO call, signal, order, time exits, reconciliation | `data/challenge/trades.jsonl` | every minute (Task Scheduler) | preflight HALT (exit 1); MT5 down | fix cause; next cycle self-heals |
| `bot_base.py` | `Bot` / `Signal` contracts | — | import time | — | — |
| `desk.py` | CIO: opportunity classification, eligibility, utility, allocation, coverage | allocation decisions | per cycle | returns 0 funded | inspect reasons in log |
| `market_state.py` | ~159-field state vector; broker clock | broker offset, desk clock | per signal | `ms_error` in state | DATA_INTEGRITY gate blocks the order |
| `macro_context.py` | Cross-asset returns/divergence | macro labels | per signal | fields None | non-blocking |
| `shadows.py` | Filter-variant verdicts recorded pre-trade | `shadows` field on each intent | per signal | verdict None | None ≠ False; not credited |
| `trading_brain.py` | Beliefs, lessons, risk audit, voiding | `data/brain/events.jsonl` (append-only) | per cycle + on demand | unreadable ledger | beliefs revert to priors |
| `head_trader.py` | Nightly review, telemetry collection, validity | `DAILY_HEAD_TRADER.md`, `data/telemetry/*.json` | daily 13:00 VPS | encoding / MT5 absent | degrades, still writes |
| `daily_review.py` | Older per-day reconstruction | `DAILY_TRADING_REVIEW.md` | manual | — | superseded by head_trader |
| `bot_i.py` | Retired candidate, kept for its funnel record | — | not registered | — | — |

**Bots** (8 live, all in `challenge_controller.py`): A/B/C/D/E BREAKOUT, F REVERSION,
G CONTINUATION, H SWEEP.

## 2. Control flow, as implemented

```
Task Scheduler (every 1 min)
        |
        v
challenge_controller.main()
        |
        +-- _start_logging()          -> data/logs/controller-<utc>.log   [ADDED 2026-08-14]
        +-- demo_gate(account)        -> HALT if not FTMO-Demo 1514166963
        +-- preflight()               -> 13 checks; HALT on any failure
        +-- time_exits()              -> close positions past their session (4 proofs required)
        +-- reconcile()               -> MFE/MAE while open; on close reconstruct from broker deals
        +-- trading_brain.learn()     -> one lesson per newly closed trade
        +-- market_state.compute()    -> per symbol, closed bars only
        +-- desk.classify_opportunity -> regimes + modifiers
        +-- desk.allocate()           -> CIO ranks by utility, caps by playbook group
        +-- bot.generate_signal()     -> only for funded bots
        +-- stop_geometry()           -> approve / widen (reduce volume) / reject
        +-- shadows.evaluate()        -> variant verdicts, recorded pre-trade
        +-- order_send()              -> or SHADOW record, or DRY RUN
        v
data/challenge/trades.jsonl (append-only; intent row + close row share intent_id)
```

## 3. Sources of truth, and the duplicates

| Fact | Canonical source | Duplicated in | Risk |
|---|---|---|---|
| Fills, exits, economics | **MT5 broker deals** | `trades.jsonl` close rows | reconcile() derives from broker; broker wins |
| Current time | **broker tick** (`broker_now_london`) | host clock | host drifts; offset is hour-rounded to discard it |
| Account drawdown anchor | **broker initial deposit** | `controller_state.json` | anchor persisted once, never recomputed |
| Beliefs | **derived** from `trades.jsonl` each read | nothing cached | cannot drift from evidence |
| Voided evidence | `brain/events.jsonl` `evidence_voided` | — | ledger never edited |

## 4. Fail closed vs fail open

**Trading-critical (block NEW entries):** wrong account, non-demo, AlgoTrading off, MT5
disconnected, clock drift vs broker, missing market state, unwritable ledger, drawdown veto,
stop geometry reject.

**Auxiliary (trading continues):** Git unavailable, Obsidian unavailable, LLM unavailable,
macro fields missing, research jobs failed.

This distinction is enforced in `preflight()` (hard exit) versus everything the orchestrator
does (best effort, logged).

## 5. Known silent-fallback defects, all now explicit

Five were found and fixed by comparing output to ground truth, never by reading code:

1. **Inert drawdown limits** — anchor recomputed from current equity; headroom always read full.
2. **Missing time exits** — `expected_holding_minutes` written, never read; a gold position held 23h.
3. **Silent anchor fallback** — `history_deals_get` given mixed naive/aware datetimes; failed into reconstruction.
4. **Broker clock read as UTC** — every session window fired 3 hours early.
5. **Rounding manufactured drift** — 15-min rounding kept part of a host skew while looking precise.

Policy now: **any fallback emits an explicit event.** No preferred source may be replaced silently.

## 6. What does not exist yet

- Structured machine-readable event log (Phase 2)
- Orchestrator health/evidence coordinator (Phase 3)
- `DAILY_VALIDATION.md` (Phase 4)
- Any VPS→Mac transport (blocked on credentials — see `HUMAN_ACTION_REQUIRED.md`)
- Obsidian bridge on the VPS (exists only as a Mac post-commit hook)
