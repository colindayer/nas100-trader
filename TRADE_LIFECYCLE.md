# TRADE_LIFECYCLE — the actual code path

Release candidate: TASK-0005 + TASK-0004 integrated. Every line reference is real; nothing
below is inferred from a file existing. One cycle, once per minute, `ChallengeController`.

```
                       challenge_controller.py::main()  :1300
                                    |
  MT5 terminal ────────────────────►│ demo_gate()          :1244  account bound, trade_mode 0
                                    │ preflight()          :1332  12 checks; FAILS -> exit 1
                                    ▼
  ┌─── POSITION MANAGEMENT — runs BEFORE any clock question, and cannot be gated ──────────┐
  │  time_exits()   :1347 → :497    host clock + ledger. Four proofs: account, symbol,     │
  │                                 ticket, session ended. Consumes NO clock-safety value. │
  │  reconcile()    :1348 → :426    broker deals → exit, gross, swap, commission, NET,     │
  │                                 R, MFE, MAE. Uses no clock at all.                     │
  │  broker SL/TP                   set at order time, never modified by any desk code.    │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                    ▼
  CLOCK / FEED STATE   MS.clock_state()  :1358
      inputs   : freshest tick across CLOCK_SYMBOLS, host UTC, persisted trusted offset
      output   : one of six states  →  data/logs/clock_state.json (atomic)
      consumer : the entry path only
      NOT FEED_FRESH → print, emit CLOCK_STATE, mt5.shutdown(), return.
                       Exits and reconciliation have ALREADY run. Nothing below executes.
                                    ▼
  MARKET STATE         MS.compute()      :1415   per symbol, closed bars only
      → ~39 field families × D1/H4/H1/M15 + levels, break quality, momentum, volatility
  MACRO                MC.compute()      :1416   cross-asset returns; calendar explicitly NULL
      → merged into the same state dict
                                    ▼
  OPPORTUNITY          DESK.classify_opportunity()      STRONG/WEAK_TREND, RANGE, TRANSITION,
                                                        COMPRESSION, EXPANSION, EXTENDED,
                                                        AT_HTF_LEVEL, macro labels
                                    ▼
  EXPOSURE             desk_exposure()   :1432   MT5 authoritative for existence, ledger for
                                                 attribution. Faults → no new orders this cycle.
                                    ▼
  ┌─── PASS 1 · OBSERVATION  :1455 ────────────────────────────────────────────────────────┐
  │  eligibility()          regime hard-block only; modifiers never block                  │
  │  symbol_feed_fresh()    :1489  PER-SYMBOL freshness. Stale → SYMBOL_FEED_STALE,        │
  │                                continue. No candidate, so never ranked, never sent.    │
  │  in_event_blackout()                                                                   │
  │  bot.generate_signal()  :1506  EVERY eligible bot evaluates. No capacity test here.    │
  │                                → candidates{}                                          │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                    ▼
  ┌─── PASS 2 · ALLOCATION  :1525 ─────────────────────────────────────────────────────────┐
  │  DESK.allocate(candidates=…, open_group_risk=expo["per_group"], beliefs=…)             │
  │      only CANDIDATES compete; idle eligible bots consume zero                          │
  │      group cap 0.15% / total 0.75%, seeded from REAL open exposure                     │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                    ▼
  stop_geometry()  :1563   30× spread, 15% D1 ATR, 2× M1 excursion. Widening cuts VOLUME.
  ChallengeState.veto()  :1575   daily ≤2×risk, total ≤3×risk, open risk, target reached
  sizing + notional cap 3× equity + volume floor
  MANDATORY_STATE completeness  — a NULL regime is not "neutral"; not sent
  shadows.evaluate()  — observational only, recorded with the intent
                                    ▼
  exposure_gate()  :1637   live + sent-this-cycle + this order ≤ caps. Last thing before:
  mt5.order_send()  :1662  THE ONLY new-entry order_send on this desk
                                    ▼
  append_trade()   intent row → data/challenge/trades.jsonl (append-only)
                   broker stop verified after fill
                                    ▼
  ── next cycles ── open position monitored by broker SL/TP; time_exits() closes on session end
                                    ▼
  reconcile()      close row shares intent_id. R computed on NET, never gross.
                                    ▼
  VALIDITY         head_trader.validity()   VALID / VOID
                   VOID is for provable instrumentation faults, never for losses.
                                    ▼
  TRADING BRAIN    voided_intents()  trading_brain:71   closed_trades() drops them
                   belief()          trading_brain:143  posterior = shrinkage of live
                                                        expectancy toward the backtest prior
                                    ▼
  CIO ALLOCATION   beliefs feed utility() ranking on the NEXT cycle
                                    ▼
  DAILY REVIEW     head_trader.py  21:00 London  → DAILY_HEAD_TRADER.md, telemetry
  ORCHESTRATOR     desk_orchestrator.py --sync  every 15 min → reports + git evidence push
```

## The two gates that make this safe

**Clock gate** sits between position management and entry evaluation. Everything above it
protects what is already open; everything below it opens something new. That placement is the
whole reason a dead feed cannot stop an exit.

**Per-symbol gate** sits inside observation, before `generate_signal`. A stale instrument
produces no candidate at all — it cannot be observed, ranked, funded or sent — while every
other specialist stays independently evaluable.
