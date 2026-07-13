# NEXT 30-DAY MONITORING PLAN

_Start: the first trading day after the parity fixes (commit 236abe3) reach the VPS.
Purpose: accumulate ONE CLEAN MONTH of live statistics and catch execution drift
early. This is the go/no-go input for funding a prop challenge — see
PRODUCTION_READINESS_REVIEW.md (blockers #1–2) and LIVE_TRADING_PARITY.md
(fill-timing gaps to watch). **Monitoring only — no strategy changes during the
window.** A mid-month code change resets the clock._

> **CLOCK RESET 2026-07-14.** Commit 614e1ba (S2 ported to daily-FVG lineage) changed live strategy entry logic mid-window. Per the rule below, the clock resets. New anchor: first full trading day the corrected code is active = **2026-07-14**. Committee shifts 2026-08-11 -> **2026-08-16** (same 33-day span). Prior anchor 2026-07-09/236abe3 is void; ledger lines before 07-14 are pre-reset and do not count toward the clean month.


---

## 0. What "clean" means
The month only counts if, for every session: scheduler ran (Last Result 0), the
broker was real (not DryRun on the live venues), brackets were attached, and no
unexplained crash occurred. Any red day is logged, explained, and — if it was an
infra failure — the day is annotated in the journal (not silently ignored).

---

## 1. What to monitor (metric by metric)

### 1.1 Signals
- **Source:** `logs/trader.log` + `logs/mt5_<session>.log` — lines matching
  `S[0-9] SIGNAL`, `BTC SIGNAL`, `SWEEP`/`OVN` entries; Telegram FILL pings.
- **Record daily:** count per strategy, instrument, timestamp, price at signal.
- **Expected baseline (from validated replay):** S5 is the workhorse (~1.5 raw
  signals/day pre-filter, far fewer after vol/regime gates); S1/S4 ~1 per 2–3
  weeks each (GEX-gated); S2/S3 sparse; BTC occasional; OVN 2 entries/week
  (Mon+Tue) by construction.
- **Alarm:** ZERO signals across the whole book for 10 consecutive trading days
  → P(zero) is low; investigate feed/filters (re-run `verify_liveness.py`).
  OVN not entering on a Monday or Tuesday → investigate immediately (it is
  calendar-driven and MUST fire).

### 1.2 Skipped signals (the filters' story)
- **Source:** the no-signal reason lines: `GEX POSITIVE`, `PAUSED - extreme VIX`,
  `short disarmed (bull)`, `vol_ok=False`, `already in position`, `SESSION COOLDOWN`,
  `WEEKEND`, `not in 08-16 UTC window`, `Opening-range bar not formed`.
- **Record daily:** tally by reason. This is the evidence that gates work — and
  the early-warning if one gate silently dominates.
- **Alarm:** `Opening-range bar (9:00 ET) not formed` appearing during 10:00–13:00
  ET on a weekday (S5 watchdog also pages this — it is the feed canary).
  `GEX calc failed` warnings on most runs → yfinance options feed degraded.

### 1.3 Orders
- **Source:** `FILL <tag> <side> <qty> <symbol> SL=... TP=...` log/Telegram lines;
  MT5 terminal Trade tab; Alpaca dashboard Orders view.
- **Record per order:** tag (S1..S5/SWEEP/BTC/OVN), side, qty, entry price,
  SL, TP, venue, timestamp.
- **Alarm:** any `NAKED ORDER` warning (order without sl) from a bracket strategy;
  any `ORDER_FAIL`/`MT5 ORDER FAIL` line.

### 1.4 Fills & slippage (parity gap #4/#5 — the thing we're measuring)
- **Record per fill:** signal price vs actual fill price → slippage in bps.
- **Weekly:** average + worst slippage per strategy. Backtest assumes ~3 bps/side
  (SLIP=0.0003). If live slippage runs >2x that consistently, the backtest edge
  must be re-costed before any funding decision.

### 1.5 Stops & targets
- **Record per closed trade:** exit type (STOP / TARGET / time-exit / manual),
  R-multiple achieved, holding time.
- **Expected:** losers = −1R (stop), winners ≈ +3R (S1/S2/S4/S5) — if realized R
  on winners is materially below the configured RR, brackets are being filled
  short of target (or TP legs are wrong) → investigate.
- **Alarm:** any position visible in MT5/Alpaca with an EMPTY S/L column;
  any S3 position on MT5 older than 5 trading days (known blocker — needs the
  manual exit: check daily).

### 1.6 Broker errors
- **Source:** `grep -iE "FAIL|error|retcode|Traceback" logs/*.log` + CRASH Telegram
  alerts (global excepthook) + GitHub Actions red runs.
- **Record:** every occurrence with retcode/reason.
- **Alarm:** repeated `retcode` rejections on one symbol (min-stop-distance or
  lot-size issue); any CRASH alert (should be near-zero now).

### 1.7 Dry-run vs live mode
- **Check:** every log header line `LIVE TRADER - broker=X dry_run=Y`.
  MT5 sessions must show `dry_run=False`, `Broker: MT5Broker`.
  Alpaca Actions: `dry_run=False`, `Broker: AlpacaBroker`. BTC-on-Actions is
  `--dry-run` BY DESIGN (geo-block) — do not count it as live.
- **Alarm:** `DryRunBroker` appearing on a venue that should be live = credential
  regression → fix same day, annotate the gap.

### 1.8 Equity & drawdown
- **Source:** the `Equity:` line each session; `logs/risk_state_<broker>.json`
  (peak + month-start); daily 17:00 ET heartbeat.
- **Record daily:** equity per account (MT5 $50k demo, Alpaca $100k paper),
  current DD vs peak, month P&L.
- **Alarm:** daily loss > 3% (kill-switch fires at 5% — 3% is the early-warning);
  drawdown approaching the 8% throttle target.

### 1.9 Risk scale (the throttle telling the truth)
- **Source:** `RISK_SCALE=` line each session (DD-throttle output).
- **Record daily:** value per venue. 1.00 = no drawdown; sliding toward 0.3 =
  throttle actively defending.
- **Alarm:** RISK_SCALE stuck at a low value while equity has recovered
  (stale peak state); RISK_SCALE=1.00 while in visible drawdown (state file broken).

### 1.10 Strategy performance (the month's actual product)
- **Weekly per strategy:** #signals, #trades, win rate, avg R, net P&L, and the
  running comparison vs backtest expectation.
- **Month-end:** live Sharpe proxy (mean/std of daily P&L, annualized) vs the
  validated backtest per-strategy Sharpe. THE go/no-go input.
- **Honesty rule:** ~20 trades minimum before win-rate comparisons mean anything;
  a 2-trade week proves nothing in either direction.

---

## 2. Daily checklist (~5 minutes, once per evening)

```
[ ] Telegram: any CRASH / ORDER FAIL / watchdog alert today?      -> if yes, triage first
[ ] VPS:   python status.py        (tasks Last Result 0, symbols resolve, logs fresh)
[ ] MT5 Trade tab: every open position shows S/L (and T/P where expected)
[ ] Any S3 position on MT5? note its age; manually close at 5 trading days
[ ] Log skim: grep -cE "SIGNAL" logs/mt5_*.log  -> record today's signal count
[ ] Note skip reasons (GEX/VIX/vol_ok/weekend) in one journal line
[ ] Equity + RISK_SCALE per venue -> journal line (vault/11-Daily-Journal)
[ ] GitHub Actions: today's runs green?
```

## 3. Weekly review checklist (~30 minutes, Friday after close)

```
[ ] Run check_health.py + verify_liveness.py on the VPS (engine still fires on recent data)
[ ] Trade ledger update: every fill -> tag, R result, exit type, slippage bps
[ ] Slippage vs 3 bps backtest assumption (per strategy)
[ ] Winners' realized R vs configured RR (bracket integrity)
[ ] Signal counts vs baseline (S5 present? OVN fired Mon+Tue? S1/S4 drought normal?)
[ ] Any same-day re-entry after a stop-out? (known parity blocker - count occurrences;
    if it happens >1x, prioritize the one-entry-per-day fix AFTER the window)
[ ] Equity curve + DD per venue; RISK_SCALE trajectory
[ ] Incident review: any red day? annotate cause in the journal
[ ] Update vault: 11-Daily-Journal weekly note + Dashboard tables
```

## 4. Month-end deliverable (day 30)

Produce `docs/MONTH_1_LIVE_REPORT.md`:
- trades, win rate, avg R, net P&L per strategy and combined
- live Sharpe proxy vs backtest Sharpe (the honest ratio)
- slippage summary vs backtest costs
- infra scorecard: crashes, red days, naked-order warnings (target: 0)
- **Decision:** live ≥ ~2/3 of backtest expectation → proceed to prop-challenge
  funding per PROP_CHALLENGE_PLAYBOOK; materially below → diagnose before ANY
  funding; near zero/negative → the edge did not survive contact, stop and reassess.

## 5. Standing rules for the window
1. **No strategy/param/filter changes.** Infra-only fixes allowed (with journal note);
   anything touching signals resets the 30-day clock.
2. **Do not fund any challenge during the window.**
3. Every manual intervention (closing a position, restarting MT5) gets a journal line.
4. If the VPS dies: brackets protect open positions; fix the host, log the outage
   window, resume — outage days don't count toward the 30.
