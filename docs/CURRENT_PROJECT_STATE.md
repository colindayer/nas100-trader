# CURRENT PROJECT STATE — 2026-07-11

_Onboarding snapshot for any agent/human joining. Sources: LIVE_TRADING_PARITY,
PRODUCTION_READINESS_REVIEW, NEXT_30_DAY_MONITORING_PLAN, LIVE_TRADE_REVIEW,
NO_REAL_TRADES_ROOT_CAUSE, STARTUP_FIX_REPORT + direct inspection of
live_trader.py / broker.py / mt5_broker.py. Working tree clean at time of writing._

## Current architecture

- **One entrypoint:** `live_trader.py` (~1100 lines) — argparse (`--session`,
  `--broker`, `--dry-run`) → session lock/cooldown + weekend skip → broker factory
  (lazy imports) → regime fetch (VIX/SPY/QQQ via yfinance) → per-broker DD-throttle
  (`update_risk_state`, `logs/risk_state_<broker>.json`) → daily/monthly kill-switch
  → session dispatch to strategy functions → daily 17:00 ET heartbeat.
- **Strategies (validated, frozen):** S1 Asian sweep (QQQ), S2 gold FVG, S3 abnormal
  volume (SL + 5-day time exit), S4 multi-sweep (QQQ+SPY), S5 ORB (long/short,
  10–13 ET window), SWEEP basket (9 tickers, Alpaca full / MT5 restricted),
  BTC sweep (state-machine + bracket + reconcile), OVN overnight (time exit + 5%
  catastrophe stop), BTC-trend + XSMOM (rebalance-managed, no broker stop).
- **Broker layer:** `Broker` ABC in `broker.py`; `place_order_safe(..., sl, tp)`
  retries, warns on naked orders, TypeError-falls-back for non-bracket adapters.
  `MT5Broker`: atomic SL/TP brackets, server-UTC offset auto-detect, symbol map
  QQQ→US100/SPY→US500/GLD→XAUUSD/BTC→BTCUSD, `RESTRICTED_UNIVERSE=True`.
  `AlpacaBroker`: BRACKET/OTO orders, **GTC**, bar-count `get_bars` contract.
  `DryRunBroker` wrapper prints intended orders. Binance/cTrader/Tradovate dormant.
- **Safety layers:** broker-side SL/TP on every bracket strategy; global
  `sys.excepthook` → Telegram CRASH alert; NAKED ORDER warning; UTF-8/ASCII output
  (post emoji-crash); S5 watchdog canary; `status.py` health command.
- **Deployment:** Windows VPS (188.190.4.122) = git clone of `main`, auto-pull /30min,
  `Nas100Bot-*` scheduled tasks (hourly all/btc, 30-min overnight, daily
  btctrend/rebal) with per-venue `logs/mt5_<session>.log`. GitHub Actions runs
  Alpaca paper (`all`, `overnight`) + BTC **dry-run by design** (Binance geo-block).
  Secrets in gitignored `config.ini` / GitHub Secrets.

## Current production status

- **Demo/paper readiness: 88/100. Funded/live readiness: 55/100. DO NOT FUND YET.**
- All venues start, protect, alert, self-update. Startup verified (STARTUP_FIX_REPORT).
- **Zero real-money fills have ever occurred.** Early "live" window: 19/21 sessions
  were operator-launched dry-runs; the 2 live sessions had no signals (filters
  correct). The Alpaca −1.5% is pre-existing account history, NOT system losses.
- Parity with the validated backtests was restored on 2026-07-09 (get_bars unit
  bug, 30-bar filter starvation, DAY→GTC brackets). **The clean 30-day statistics
  window starts with the first trading day after commit 236abe3 — it is running now.**
  Governing doc: NEXT_30_DAY_MONITORING_PLAN.md.

## Confirmed remaining blockers

1. **No clean month of live statistics** (the funding gate — calendar time, not code).
2. **One-entry-per-day divergence:** backtest takes ≤1 entry/strategy/day; live can
   re-enter after a same-day stop-out. Fix needs new per-day state — reviewed change,
   after the window unless it actually occurs (weekly checklist counts it).
3. **S3 on MT5 has no time exit / no target** (Alpaca-only exit path). Manual daily
   check per monitoring plan; treat S3 as Alpaca-only.
4. **S3 signal provenance:** live z-score basket matches neither validated lineage.
5. **BTCTREND/XSMOM lack broker-side stops** (rebalance-managed; keep off funded).
6. **`risk/` mode package (challenge/funded/live) is dormant** — never imported.
7. **Single-VPS SPOF**; secrets pasted in old chats need rotation before real money.
8. First Alpaca BRACKET/GTC fill not yet observed live (code verified, fill pending).
9. ~~Fill ledger~~ RESOLVED 2026-07-10: logs/fills.csv now records signal-vs-fill execution costs at the order boundary (forensics recommendation implemented).

## Files that matter

| File | Role |
|---|---|
| `live_trader.py` | the entire live engine (entry, risk, dispatch, strategies) |
| `broker.py` | ABC + `place_order_safe` + DryRun wrapper + config loader |
| `mt5_broker.py` / `alpaca_broker.py` | the two live venue adapters |
| `alerts.py` | Telegram/email sink |
| `config.ini` (gitignored) | all credentials + `[risk]` config |
| `schedule_mt5.ps1`, `.github/workflows/main.yml` | schedulers (VPS / Actions) |
| `status.py`, `s5_watchdog.py`, `check_health.py`, `verify_liveness.py`, `diag_live.py` | ops/verification; `scripts/ops/daily_check.py` -> docs/DAILY_OPS_REPORT.md (nightly report-only verdict) |
| `protect_positions.py`, `test_order.py` (demo-guarded) | emergency/manual tools |
| `full_yearly.py`, `master_backtest.py` | the two validated backtest lineages (reference) |
| `docs/*` + `vault/` | governance: parity, readiness, monitoring plan, Obsidian OS |
| `scripts/obsidian/build_obsidian.py` | Obsidian Bridge: generates vault/auto/ knowledge base (idempotent, AUTO-marker sections; runs via git post-commit hook) |
| `research/` + `scripts/research/new_idea.py`, `new_paper.py` | Research OS v1: idea/paper intake with gauntlet-checklist templates (research firewall: never the live path); experiment pipeline queue->experiments->archive via new_experiment.py/promote_experiment.py (lifecycle + reviewer gates); AI Task Router scripts/router/ dispatches TASK-* items to Claude/GLM/Qwen/Fable/OpenClaw AND auto-executes whitelisted actions (executor.py: capture+status+follow-up chains; production-blind) |

Everything else in the 143-file root is research/experiment sprawl — inventoried in
CODE_INVENTORY.md, scheduled for archiving in MIGRATION_PLAN Phase 2 (not yet run).

## Branches

- `main` — production; the VPS auto-pulls this. Clean, up to date with origin.
- `ai/dashboard` (local) + `origin/claude/prop-firm-challenge-optimization-x3kn5h`
  (remote) — stale side branches from earlier agent sessions; nothing on them is
  needed by production.

## Recent commits (newest first)

```
1a7174c  Head of Research program: universe expansion (11 keepers, pooled 2.32, corr 0.14), macro segmentation (3 NEEDS_MORE_EVIDENCE), TSMOM candidate (ETF-only; CFD killed by financing)
d9df262  Obsidian bridge auto-sync [bridge-auto]
d1ba90c  EXP-20260711-01 adversarial review: VALIDATED_FOR_FORWARD_SHADOW — look-ahead found+corrected (C 1.39 vs B 1.02, 6/6), survives episode leave-outs + 2x costs; level gate confirmed harmful to S5
703cbd0  Obsidian bridge auto-sync [bridge-auto]
2f623e8  EXP-20260711-01 run: VIX term-structure gate — S1 no value; S5 beats level gate 6/6 splits (1.50 vs 1.04); current level gate HURTS S5 (awaiting review)
87e98ae  Obsidian bridge auto-sync [bridge-auto]
2d97b34  Macro regime survey: 6 filter families reviewed, 1 survivor (VIX term-structure gate); 2 paper notes + 1 idea
c346b7a  Obsidian bridge auto-sync [bridge-auto]
```

## What should NEVER be changed (without explicit human sign-off + clock reset)

1. **Strategy entry logic, filters, and the validated constants**
   (`RISK_S*`, `STOP_S*`, `RR_*` — lineage: `master_backtest.py`). Frozen.
2. **Broker-side SL/TP on every bracket order** — never remove, never make optional.
3. **The kill-switches and DD-throttle** (daily 5%, monthly 4%, target DD 8%).
4. **ASCII-only production output** (emoji crashed the scheduler for 6 days).
5. **`get_bars` = BAR COUNT contract** on every adapter.
6. **Secrets stay out of git** (config.ini gitignored / GitHub Secrets).
7. **During the 30-day window: any signal-touching change resets the clock.**
8. The BTC reconcile guard (state cleared when broker shows flat — prevents
   accidental shorts on the hedge account).

## Next highest priority task

**Execute the 30-day monitoring plan — daily checklist, weekly reviews — and let the
statistics accumulate.** No engineering task outranks this; the system's only open
question is whether the validated edge survives live execution, and only calendar
time answers it. Secondary (allowed, infra-only): confirm the first Alpaca GTC
bracket fill shows SL/TP correctly, and keep the S3-age daily check. Everything else
(risk-mode wiring, Phase-2 archive, one-entry-per-day fix) waits for the month-end
go/no-go in `MONTH_1_LIVE_REPORT.md`.
