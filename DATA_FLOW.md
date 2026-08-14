# DATA FLOW

_How information moves, and where it currently stops._

## 1. Trade lifecycle

```
MT5 tick/bars ──> market_state.compute()  (CLOSED bars only, broker clock)
                        │
                        ├──> desk.classify_opportunity()  ──> regimes + modifiers
                        │                                      │
                        │                                      v
                        │                                 desk.allocate()  (CIO)
                        │                                      │ funded?
                        v                                      v
                  bot.generate_signal() ──> Signal ──> stop_geometry() ──> shadows.evaluate()
                                                                                 │
                                                    ┌────────────────────────────┘
                                                    v
                                    INTENT ROW appended to trades.jsonl
                                    (market_state + shadows + CIO reason embedded)
                                                    │
                                                    v
                                              mt5.order_send()
                                          ┌─────────┴─────────┐
                                     retcode 10009        rejected
                                          │                   │
                                     ticket stored     retcode stored, NOT a trade
                                          │
                          ┌───────────────┴───────────────┐
                    every cycle:                    session end:
                    reconcile() samples             time_exits() closes
                    MFE/MAE                         (4 proofs required)
                          │                               │
                          └───────────────┬───────────────┘
                                          v
                          CLOSE ROW appended (same intent_id)
                          exit, gross, swap, commission, NET, R, MFE_R, MAE_R, holding
                          reconstructed from BROKER DEALS, not from our own model
                                          │
                                          v
                              trading_brain.learn()  ──> brain/events.jsonl
                                          │
                                          v
                          belief() re-derived from the whole ledger on every read
                                          │
                                          v
                          desk.allocate() reads it on the NEXT cycle
```

**Two rows per trade, never edited.** The intent as decided, and the outcome as the broker
reported it. `closed_trades()` merges them by `intent_id`.

## 2. R is computed on NET

`R = net / (risk_pct × account_equity_at_entry)` where `net = gross + swap + commission`.

Gross R would flatter every bot by exactly the amount FTMO charges. This is the error that
made the frozen portfolio look viable for a month.

## 3. Evidence that currently goes nowhere

| Produced | Written to | Reaches the human? |
|---|---|---|
| Per-cycle decisions | `data/logs/controller-*.log` | only by RDP + `type` |
| Trade ledger | `data/challenge/trades.jsonl` | only by RDP |
| Brain events | `data/brain/events.jsonl` | only by RDP |
| Telemetry | `data/telemetry/<date>.json` | only by RDP |
| Nightly review | `DAILY_HEAD_TRADER.md` | only by RDP |

**All of it is under `data/` or on the VPS filesystem, and `data/` is gitignored.**
That single line is why the human is still the transport.

## 4. Intended flow once credentials exist

```
VPS                                       GitHub                    Mac / Obsidian
───                                       ──────                    ──────────────
controller writes logs+ledger   ──push──> reports/ + evidence/ ──pull──> vault/
head_trader writes reviews                                              post-commit hook
orchestrator commits artifacts                                          already installed
```

Blocked on one GitHub token. See `HUMAN_ACTION_REQUIRED.md`.

## 5. Clock derivation

```
mt5.symbol_info_tick(sym).time          # broker server epoch, several symbols
        │  max() across CLOCK_SYMBOLS   # freshest market wins; closed markets cannot stale it
        v
raw delta vs host UTC ──> round to WHOLE HOUR ──> broker_utc_offset
        │                                          (host drift up to ±30 min discarded)
        v
desk_now_london = broker_tick − offset → Europe/London
```

Read **once per cycle** and shared by every bot. A per-symbol clock gave EURUSD 23:58 while
US500 read 22:49 in the same cycle.
