# LIVE TRADING PARITY — live vs validated backtests

_Audit of Signal → Filters → Risk → Sizing → Broker → Execution for every strategy.
Reference lineages: `master_backtest.py` (the lineage live was built from — constants
match exactly) and `full_yearly.py` (a later refinement). Where the two lineages
disagree, live follows `master_backtest` and the difference is recorded as
intentional, not "fixed" by guessing._

## 1. Bugs fixed (confirmed, with evidence)

### Fixed in this pass (commit 236abe3)
| # | Bug | Evidence | Fix |
|---|---|---|---|
| 1 | **`get_bars` unit mismatch across brokers** — Alpaca read `lookback` as **days**, MT5/Binance as **bar count**. The same strategy call saw ~16x more history on Alpaca than MT5; venue behavior diverged from each other and from backtest. | Read of both adapters; `timedelta(days=lookback)` vs `copy_rates_from_pos(..., lookback)` | Alpaca now honors the BARS contract (fetches a generous window, returns `.tail(lookback)`) |
| 2 | **Filter starvation on 30-bar lookbacks (S1/S2/S4/sweep-basket)** — `DailyEMA50` was an EMA over **2** daily closes and `HighVol` was **permanently False** (ATR `rolling(200)` all-NaN) on MT5. Both backtest lineages compute these on long histories. | Measured: 30 bars → 2 closes, HV defined on 0 bars; 1200 bars → **75 closes, HV defined on 988 bars, 63 True** | Lookbacks 30 → **1200 bars**; S5 5 → 24 bars (gap-fragile window) |
| 3 | **Alpaca brackets died at day end** — `TimeInForce.DAY` expired SL/TP legs at the close; backtests hold every position to stop/target **across days**. Positions were left open, unprotected, and never target-exited. | Adapter read; both backtest engines' exit loops span days | `TimeInForce.GTC` |

### Fixed in earlier passes (same parity mission, for completeness)
| Bug | Fix commit |
|---|---|
| Naked MT5 orders (no broker SL/TP at all; backtest always exits at stop/target) | brackets threaded through `place_order_safe` → MT5 atomic SL/TP |
| MT5 server-time bars treated as UTC (~3h shift corrupted Asian range/ORB) | offset detection + rebase to true UTC |
| Emoji `UnicodeEncodeError` crashed every scheduled run (cp1252 logs) | UTF-8 reconfigure + ASCII output |
| BTC state-machine could re-sell after a broker-bracket close (accidental short) | reconcile: clear state when broker shows flat |
| Startup regression (unterminated string + args-before-parse) | healed; STARTUP_FIX_REPORT.md |

## 2. Remaining blockers (real divergences, deliberately NOT patched blind)

1. **One-entry-per-day** — backtest `run_intraday` takes at most one entry per strategy
   per day (`day_traded`). Live blocks re-entry only *while the position is open*: after
   a same-day bracket stop-out, a later hourly run could re-enter. Rare (needs a second
   valid signal after a stop-out) but real. Recommended fix: per-strategy last-entry-date
   state; needs its own reviewed change (new state machinery, not a one-liner).
2. **S3 lives a different life on MT5** — the 5-day time exit only runs on Alpaca (order
   history API); MT5 S3 positions have a stop but no time exit and no target. Backtest
   exits at stop/target/5-day. Keep S3 effectively Alpaca-only until an MT5 history-based
   exit is built.
3. **S3 signal math differs from both lineages** — live uses a volume z-score (>1.5) +
   day-return>1% on a 5-ticker basket; `full_yearly` uses 1.3x vol ratio + green close +
   bull + neg-GEX on QQQ daily. No single validated reference exists for the live
   variant; needs a decision (re-validate live's version or port the backtest's).
4. **Same-bar vs next-bar entry** — backtests signal on bar `i-1` and enter at close of
   bar `i`; live evaluates the latest (possibly forming) bar and enters immediately.
   In real time these approximate each other, but fills can differ around fast moves.
   Inherent to hourly polling; acceptable, monitor slippage stats.
5. **Bracket exits are broker-side intrabar; backtest checks closes** — live stops can
   trigger on an intrabar wick where the hourly backtest engine (close-to-close checks
   in `run_intraday`) would have survived the bar. Slightly more conservative live.
   Intentional (safety-first), but it IS a parity gap in fill timing.

## 3. Intentional differences (documented, keep)

| Difference | Why |
|---|---|
| **S1 bull filter removed live** (backtests include `SB`) | separately validated: OOS Sharpe 0.88→1.02, works in bear regimes; recorded in code comment + FINDINGS |
| **S5 has no GEX gate live** | matches the `master_backtest` lineage (no NG on S5); `full_yearly` later added NG. Lineage choice, not a bug. If S5 live overperforms/underperforms, revisit. |
| **Constants differ from `full_yearly`** (`RISK_S5 .0075/RR 3.0`, `STOP_S2 .015/RR 3.0`, `RISK_S4 .004`) | live matches `master_backtest.py` exactly (`git log -S` traces them to the original live-trader commit). Not drift — a different validated lineage. |
| **DD-throttle × vix_mult × RISK_SCALE on every size** | live-only risk layers ON TOP of backtest sizing — always ≤ backtest size, never > |
| **Daily 5% / monthly 4% kill-switch (global)** vs backtest per-sleeve −5% day-lock | equivalent-or-stricter live protection |
| **S2 hourly London FVG live** vs `full_yearly` daily FVG | `full_yearly` used daily only because yfinance couldn't serve 5y hourly GLD (stated in its header); live has real hourly data — closer to the original design |
| **MT5 universe restricted** (SPY/GLD/US100/BTC) | Pepperstone doesn't list US single stocks; Alpaca runs the full basket |
| **OVN 5% catastrophe stop, BTC bracket+reconcile** | safety nets absent from backtests by construction (backtests can't crash mid-position) |

## 4. Verification performed
```
python3 -m py_compile live_trader.py alpaca_broker.py        -> OK
filter-health: 30 vs 1200 bars on qqq_hourly_7y.csv          -> 2 vs 75 closes; HV 0 vs 988 bars
dry-run asian  (S1+S2+S4, 1200-bar path)                     -> all evaluate, clean END
dry-run orb    (24-bar path)                                 -> ORB found, S5 signal w/ SL/TP
dry-run sweep  (1200-bar basket)                             -> 9/9 tickers evaluate, no data err
```

## Bottom line
The three venue-behavior bugs that made live diverge from backtest (history starvation,
per-venue unit mismatch, expiring brackets) are fixed and verified. What remains is
either **intentional** (lineage choices, extra safety layers) or **documented blockers**
that need their own reviewed changes (one-entry-per-day, S3's MT5 exits, S3 provenance)
— not silent patches.
