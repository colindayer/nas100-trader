# OPERATIONS

## 1. Daily
Nothing. The desk trades, reconciles, learns and reviews itself.
Read `DAILY_VALIDATION.md` (once Phase 4 lands) or `DAILY_HEAD_TRADER.md`.

## 2. Scheduled tasks (VPS)

| Task | Schedule | Command | Verify |
|---|---|---|---|
| `ChallengeController` | every 1 min | `python challenge_controller.py --live-demo` | `Get-ScheduledTaskInfo` → `LastTaskResult 0` |
| `HeadTraderReview` | daily 13:00 VPS (21:00 London) | `python head_trader.py` | `DAILY_HEAD_TRADER.md` mtime |

**Both must use `LogonType S4U`**, otherwise they only run while a user session exists:

```powershell
Set-ScheduledTask -TaskName "ChallengeController" -Principal (New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType S4U -RunLevel Highest)
```

Also clear the battery settings — meaningless on a VPS, but they will stop the task if the
hypervisor ever reports battery state:

```powershell
$t = Get-ScheduledTask -TaskName "ChallengeController"; $t.Settings.DisallowStartIfOnBatteries = $false; $t.Settings.StopIfGoingOnBatteries = $false; Set-ScheduledTask -TaskName "ChallengeController" -Settings $t.Settings
```

## 3. Failure playbook

| Symptom | Cause | Fix |
|---|---|---|
| `PREFLIGHT FAILED: algotrading_enabled` | AlgoTrading toggle off | MT5 toolbar + Tools→Options→Expert Advisors→Allow algorithmic trading |
| `PREFLIGHT FAILED: fresh_m1_data` | feed stalled or market closed | check MT5 connection; benign outside market hours |
| `PREFLIGHT FAILED: market_state_complete` | `ms_error`, or too few bars | check `d1_bars` in the log line; usually broker history depth |
| `HOST CLOCK is N min from the broker's` | VPS clock drift | `w32tm /resync`; windows unaffected (offset hour-rounded) |
| retcode 10027 on every order | AlgoTrading off | as above; does NOT consume a bot's 3 daily attempts |
| retcode 10016 | stop inside broker `stops_level` | widen; `stop_geometry` should have caught it |
| Position past its session | `time_exits` failed | check the 4 proofs in the log: magic/ledger/symbol/session |
| Bot silent all session | see `no_signal_reason` in the log | each reason is explicit |

## 4. Recovering the desk on a new VPS

1. Install Python 3.13 + MetaTrader5 package + MT5 terminal, log into FTMO-Demo 1514166963.
2. Clone the repo (see the size warning in `ARCHITECTURE.md` §0).
3. `config/guardian.env` must contain `ACCOUNT_LOGIN=1514166963` and `ACCOUNT_SERVER_CONTAINS=FTMO`.
4. Register both scheduled tasks with `S4U`.
5. Run `python challenge_controller.py --dry-run` and confirm `PREFLIGHT OK`.
6. **Do not copy `controller_state.json`** — let the anchor re-derive from the broker deposit.

## 5. Voiding evidence

Only for a **provable instrumentation fault**, never for a loss.

```
python trading_brain.py --void-existing "<reason>"
```

Appends an event; the ledger is never edited. `closed_trades(include_voided=True)` recovers
everything.

## 6. Safety invariants — never remove

- demo gate every cycle (account identity + `trade_mode == 0`)
- `time_exits` requires 4 proofs before closing anything
- shadow bots never reach `order_send`
- `PATCHES.md` is advisory; nothing auto-applies
- LLM output is advisory; nothing auto-applies
