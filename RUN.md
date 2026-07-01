# nas100-trader — Run Reference

A multi-strategy, broker-agnostic systematic trading bot. Validated edges stacked
into a diversified book (combined Sharpe 1.66, -5.8% DD, prop-viable).

## Setup (once)
```
pip install -r requirements.txt          # pandas numpy yfinance scipy alpaca-py requests
# put credentials in config.ini (gitignored) — see config.example.ini
```

## The one command that runs everything
```
python live_trader.py --broker <BROKER> --session <SESSION> [--dry-run]
```
- `--broker`: `alpaca` (US ETFs/stocks, paper), `mt5` (Pepperstone CFDs/prop),
  `binance` (crypto), `ctrader`
- `--dry-run`: print intended orders, place nothing (paper-track)

## Sessions (what each runs)
| session | what it does | when to schedule |
|---|---|---|
| `all` | S1 sweep + S2 gold + S3 vol + S4 multi-sweep + S5 ORB + **sweep basket** | 3×/day (07:30, 14:30, 21:00 UTC) |
| `sweep` | S1 Asian-sweep on the validated basket (SPY/IWM/GLD/XLK/XLE/AAPL/MSFT/NVDA/AMZN) | with `all` |
| `overnight` | long QQQ→NAS100 into Tue+Wed mornings | close 15:55 ET + open 10:00 ET |
| `btctrend` | vol-targeted Donchian trend on BTC | daily |
| `btc` | BTC Asian-sweep | hourly (08-16 UTC) |
| `rebal` | monthly cross-asset momentum | 1st of month |

## Deploy (hands-off)
- **Alpaca (equities):** GitHub Actions `.github/workflows/main.yml` (cloud, auto-pulls code).
- **MT5 (prop):** Windows VPS scheduled tasks running `--broker mt5 --session {all,overnight}`.
- **BTC:** Railway/VPS (Binance geo-blocks US cloud; yfinance fallback in binance_broker).

## Risk / prop config (`config.ini [risk]`)
```
target_drawdown = 0.08   # DD-throttle keeps live DD near this (safe under 10% prop limit)
daily_loss_limit = 0.05  # halt new orders if daily loss exceeds
monthly_loss_limit = 0.04
```
The conformal DD-throttle auto-sizes RISK_SCALE to hold the target drawdown.

## Backtests / research
```
python full_yearly.py            # S1-S5 combined, per year
python alpaca_universe_sweep.py  # sweep across a large universe (Alpaca free extended-hours)
python cot_oil_strategy.py       # (rejected) COT oil — example of the gauntlet
```
Discipline: every new edge must pass IS/OOS walk-forward + costs + correlation
(<0.3 to QQQ) + regime check. See EDGE_HUNT_BRIEF.md.

## Validated book (as of 2026-07)
- S1 sweep (9 tickers, all regimes): Sharpe ~1.0
- Overnight (Tue/Wed): Sharpe 0.68 | BTC trend (vol-targeted): Sharpe 0.67
- **Combined (risk-parity, corr ~0.05): Sharpe 1.66, -5.8% DD, +9.5%/yr**
- Prop-ready (throttle at 8%): ~+16%/yr at ~10% DD
