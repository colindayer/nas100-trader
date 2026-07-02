# MT5 Data + Execution Bridge — VPS Quickstart

The bridge is two-way: **data** (broker-real 24h CFD history out of the MT5
terminal → CSVs for validation) and **execution** (`--broker mt5` in
`live_trader.py`, already implemented). Validating and trading on the SAME
feed removes the biggest live-vs-backtest gap and is the honest way to speed
up the challenge — not extra risk.

## 0. Get the right files (your `iwr` pulled from `main` — the new tools live on the work branch)

Grab the whole branch once instead of file-by-file:

```powershell
iwr https://github.com/colindayer-boop/nas100-trader/archive/refs/heads/claude/prop-firm-challenge-optimization-x3kn5h.zip -OutFile branch.zip
Expand-Archive branch.zip -DestinationPath . -Force
# the zip expands into a SUBFOLDER — copy its contents over your working folder:
Copy-Item .\nas100-trader-claude-prop-firm-challenge-optimization-x3kn5h\* . -Recurse -Force
```

⚠️ Re-download after every update — in particular `mt5_broker.py` now contains
the **server-time fix**: MT5 bar timestamps are SERVER time (UTC+2/+3), not
UTC. Without the fix every session window (Asian range, ORB hour) is shifted
~3h and the Asian high/low is computed from the wrong bars — that's the
`close=29124 / asian_low=29700` weirdness you saw. The offset is auto-detected
from a live tick (override with `[mt5] server_utc_offset` or `--utc-offset`).

## 1. Fixes for the two errors on your screen

| You typed | Correct |
|---|---|
| `python live_trader.py --broker binance --session btctrend` | `python live_trader.py --broker binance --session btc` |
| `check_health.py` | `python check_health.py` (and the file is on the branch, step 0) |

## 2. ⚠️ Never test orders on the FundedNext eval login

The `place_order('QQQ',0.1,'buy','TEST')` one-liner is fine **on a demo login
only**. On the eval it's a real ticket: it can log a trading day, collide with
news-window rules, and waste drawdown on spread. Keep a separate MT5 demo
(same broker server) in `config.ini` for tests; switch credentials only when
going live for real.

## 3. Pull the data (the actual bridge)

```powershell
pip install MetaTrader5 pandas pytz
python fetch_mt5_history.py                      # US100 + XAUUSD + BTCUSD, 4y H1
python fetch_mt5_history.py --symbols US100 --alias qqq   # + qqq_hourly_7y.csv alias
```

If a symbol errors, `python mt5_broker.py` lists your broker's exact names
(e.g. `NAS100`, `USTEC`) — set `[mt5] map_qqq = NAS100` in `config.ini`.
If history comes back short: open the symbol's H1 chart in the terminal,
scroll back to force a download, re-run.

## 4. Validate ON that data (minutes, on the VPS)

```powershell
python verify_liveness.py            # entry logic fires on the broker feed?
python intraday_momentum_test.py     # the SSRN lead, now on US100 CFD data
python check_health.py               # scheduler/gates/silence triage
```

`verify_liveness.py` on the US100 alias answers your "too strict to fire?"
question against the exact instrument you trade — if it shows recent signals
there but your live log shows none, the gap is ops (scheduler/session times),
not the strategy.

## 5. Dry-run, then schedule all sessions

```powershell
python live_trader.py --broker mt5 --dry-run --session asian
python live_trader.py --broker mt5 --dry-run --session orb
```

Your Task Scheduler shows only `Overnight-MT5` (every 30 min). The pillars
need the other sessions too — check `schedule_mt5.ps1` registers **asian**,
**orb**, **eod** (and **btc** hourly 08–16 UTC if BTC runs via this account).
A missing scheduled session is the most likely cause of a silent week.

## 6. Challenge settings (from PROP_PLAN.md)

`config.ini`: keep the dd-throttle on; set challenge sizing via RISK_SCALE
1.5–2.0 (see `prop_firm_optimizer.py` output). Drop to 1.0x the day you're
funded. MT5 timezone note: FundedNext servers run UTC+2/+3 (EET) — the daily
loss limit resets at **server midnight**, which is what `daily_loss_limit`
should be aligned to, not New York midnight.
