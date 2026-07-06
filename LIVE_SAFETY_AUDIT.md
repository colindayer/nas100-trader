# LIVE SAFETY AUDIT — execution vs. backtest (money-loss focus)

_Scope: find live-vs-backtest execution mismatches that can lose money. No redesign.
No code changed by this audit (nothing found that opens an **undocumented** naked
position). Residual risks flagged as blockers for human decision._

## 1. Per-strategy: backtest exit vs live exit vs broker protection

| Strategy | Backtest exit | Live exit impl | Broker-side SL/TP | Open risk if VPS dies | Verdict |
|---|---|---|---|---|---|
| **S1** Asian sweep (QQQ→US100) | stop −1.5% / TP 3:1 | broker bracket at entry | ✅ SL+TP | none — broker holds stop | 🟢 |
| **S2** Gold FVG (GLD→XAUUSD) | stop −1.5% / 3:1 (long+short) | broker bracket | ✅ SL+TP | none | 🟢 |
| **S3** Abnormal vol | stop −2% / 5-day time hold | broker SL; time-exit needs bot | ✅ SL only | **loss capped by SL**; only the 5-day exit needs bot | 🟢 |
| **S4** Multi-sweep | stop −1.5% / 3:1 | broker bracket | ✅ SL+TP | none | 🟢 |
| **S5** ORB (QQQ→US100) | stop −1% / 3:1 (long+short) | broker bracket | ✅ SL+TP | none | 🟢 |
| **SWEEP** basket | stop −1.5% / 3:1 | broker bracket | ✅ SL+TP | none | 🟢 |
| **BTC** sweep | stop −2.5% / 3:1 | broker bracket + state-machine reconcile | ✅ SL+TP | none — broker holds stop | 🟢 (fixed) |
| **OVN** overnight | exit next-morning (time) | bot closes next AM + 5% catastrophe stop | ✅ wide SL | capped ~5% if bot down | 🟢 (fixed) |
| **BTCTREND** | vol-target Donchian rebalance | **state-machine** (rebal each run) | ❌ none | **MED** — trend position can run against you with no stop | 🟡 |
| **XSMOM** rebal | monthly rebalance | bot rebalances (Alpaca paper) | ❌ none | **LOW** — Alpaca paper, diversified, monthly | 🟡 |

## 2. Orders placed without broker-SL — do they have a documented exit?

Every order that lacks a broker-side SL **does** have a documented exit, so none are
*undocumented* naked (the bar for a forced code change):
- BTC entry (`live_trader.py:621`) → state-machine in `run_btc` (stop/target via `logs/btc_*_state.json`).
- OVN entry (`:726`) → time exit next morning in `run_overnight`.
- BTCTREND (`:779`) → rebalance-to-target state-machine.
- XSMOM (`:679/681`) → monthly rebalance.
**But "documented" ≠ "protected if the bot dies."** See §7 blockers.

## 3. All `place_order_safe` calls

| line | tag | symbol | side | sl? | tp? | acceptable? |
|---|---|---|---|---|---|---|
| 290 | S1 | QQQ | buy | ✅ | ✅ | 🟢 |
| 354/359 | S2 | GLD | buy/sell | ✅ | ✅ | 🟢 |
| 424 | S3 | sym | buy | ✅ | — | 🟢 (time exit) |
| 491 | S4 | sym | buy | ✅ | ✅ | 🟢 |
| 542/548 | S5 | QQQ | buy/sell | ✅ | ✅ | 🟢 |
| 844 | SWEEP | sym | buy | ✅ | ✅ | 🟢 |
| 586/589 | BTC | BTC | sell | — | — | 🟢 (these are **exits/closes**) |
| 621 | BTC | BTC | buy | ❌ | ❌ | 🔴 (entry, no broker stop) |
| 679/681 | XSMOM | sym | buy/sell | ❌ | ❌ | 🟡 (Alpaca rebal) |
| 726 | OVN | QQQ | buy | ❌ | ❌ | 🔴 (entry, no broker stop) |
| 779 | BTCTREND | BTC | buy/sell | ❌ | ❌ | 🟡 (rebal) |

## 4. Broker adapters — bracket support

| Adapter | Accepts sl/tp? | Attaches broker-side? | Notes |
|---|---|---|---|
| **MT5** | ✅ yes | ✅ SL+TP in one atomic `TRADE_ACTION_DEAL` (rejected order ≠ naked fill) | the live prop path — protected |
| **Alpaca** | ❌ no | ❌ falls back to naked via `place_order_safe` TypeError catch | **paper only**; equities on GitHub Actions. Naked but not real money |
| **Binance** | ❌ no | ❌ | not in live use (BTC runs on MT5) |
| **Tradovate** | ❌ no | ❌ | not in live use |
| **cTrader** | ❌ no | ❌ | not in live use |

Only **MT5** enforces brackets. The TypeError fallback in `place_order_safe` means
non-MT5 brokers place plain orders — safe *only* because they are paper/unused.

## 5. Did the SL/TP fix change any entry logic? — NO

Confirmed: the fix added **only** `sl=`/`tp=` keyword args to `place_order_safe`
calls. **No entry condition, GEX/VIX gate, sweep test, volume filter, or regime
check was touched.** Entry behavior is byte-identical to the validated version. 🟢

## 6. Scheduled jobs (VPS `schedule_mt5.ps1`)

| Task | Session | Can open a position? | Protected? |
|---|---|---|---|
| Nas100Bot-MT5 | all (S1–S5+sweep) | yes | ✅ broker SL/TP |
| Nas100Bot-BTC | btc | yes | 🔴 no broker stop |
| Nas100Bot-Overnight | overnight | yes | 🔴 no broker stop |
| Nas100Bot-BTCTrend | btctrend | yes | 🟡 no broker stop |
| Nas100Bot-Rebal | rebal (xsmom) | yes (Alpaca) | 🟡 no broker stop |
| Nas100Bot-S5Watchdog | — | no (read-only alert) | n/a |
| nas100-update | — | no (git pull) | n/a |

## 7. Emergency scripts

| Script | Opens trades? | Marked? | Could hit real money? |
|---|---|---|---|
| `protect_positions.py` | No — only **adds SL** to existing positions (`TRADE_ACTION_SLTP`) | "one-time cleanup" | Benign even on live (only *adds* protection) |
| `test_order.py` | **Yes — places a real min-lot order** | "DEMO ONLY" in docstring | ⚠️ **YES if config.ini points to a LIVE account** — it has NO demo-mode guard. Run only on demo. |

`test_order.py` orders DO carry SL/TP (not naked), so no code change forced — but
treat it as live-capable: verify `[mt5] server = *-Demo` before running.

## REMAINING BLOCKERS (ranked)

1. **✅ RESOLVED — BTC entry now carries broker SL+TP** (`live_trader.py:621`) plus a
   state-machine reconcile: if the broker bracket closes the position, the bot clears
   state instead of selling (which would have opened a short on the hedge account).
2. **✅ RESOLVED — OVN now carries a wide 5% catastrophe stop** (`:726`) as a VPS-death
   safety net; normal overnight moves never reach it, so the time-exit is unchanged.
3. **🟡 BTCTREND / XSMOM** rely on bot-managed rebalance; lower urgency (trend/paper).
4. **🟡 Alpaca places naked (paper only).** Add bracket support to `alpaca_broker.py`
   before Alpaca ever trades real money.
5. **🟡 `test_order.py`** has no demo guard — operational discipline only.

## VERIFICATION COMMANDS (run on the VPS)

```
git pull
python test_order.py QQQ buy      # places 1 demo NAS100 order -> Trade tab shows S/L + T/P
python status.py                  # MT5 conn, symbol maps, task LastResult=0, log tails
python protect_positions.py       # safety net: attach SL to ANY currently-naked position
```
After `test_order.py`, close the test position (right-click -> Close Order).

## PROP-FIRM READINESS VERDICT

- **Core prop book (US100 sweep+ORB, XAUUSD) — SAFE.** Every S1/S2/S4/S5/SWEEP order
  now enters with a broker-enforced stop + target. Survives a VPS outage. ✅
- **Auxiliary pillars (BTC, OVN, BTC-Trend) — NOT prop-safe yet.** They can hold an
  unprotected position through a bot outage. **Do not run these on a funded account**
  until they carry broker-side stops (blockers #1–3).
- **Separate from safety: the edge is still unconfirmed live.** This audit only proves
  the *execution* is now faithful for the core book — not that the strategy is profitable.

**Bottom line:** the money-losing execution bug (naked equity orders) is fixed for the
core prop book. Before funding: close blockers #1–2 (BTC + OVN broker stops), keep the
auxiliary pillars on demo, and let the core book accumulate a clean month.
