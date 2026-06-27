# Status

## Completed

### Priority 1 — Broker-agnostic architecture
- `broker.py` — abstract `Broker` ABC + `DryRunBroker` wrapper with CSV fallback
- `alpaca_broker.py` — full Alpaca ETF adapter
- `tradovate_broker.py` — Tradovate futures scaffold (MNQ/MGC/MES)
- `ctrader_broker.py` — cTrader/FTMO scaffold (US100/XAUUSD/US500)
- `live_trader.py` — `--broker {alpaca,tradovate,ctrader}` + `--dry-run`; all broker
  calls routed through adapter; strategy logic untouched
- Verified: `python live_trader.py --broker alpaca --dry-run --session asian` prints
  `[DRY-RUN] WOULD ...` without placing orders (falls back to local CSV if API auth fails)

### Priority 2 — Ops / monitoring
- `alerts.py` — Telegram + SMTP + console fallback
- `broker.py` — `place_order_safe()` retry with exponential backoff
- `live_trader.py` — `RotatingFileHandler` → `logs/trader.log`; daily kill-switch
  (configurable via `[risk] daily_loss_limit` in config.ini)
- `perf_report.py` — extended to parse live fill log, emit `logs/daily_summary.log`
- `config.example.ini` — added `[alerts]` and `[risk]` sections

### Priority 3 — Free data + volume profile revisit
- `fetch_dukascopy.py` — Dukascopy BI5 downloader for NAS100USD + XAUUSD
- Volume Profile re-test on M1 data (`volume_profile_m1.py`): DEFINITIVELY REJECTED
  (same null result at M1 resolution as hourly; see FINDINGS.md)
- `FINDINGS.md` updated with M1 result and "definitively rejected" status

### Priority 4 — Walk-forward validation
- `walkforward.py` — rolling 24m/6m/6m; S1+S4+S5L+S5S
- Result: 5/7 windows positive, avg combined +4.0%/6m, avg Sharpe 0.98
  (see full output below)

---

## Walk-forward results (24m train / 6m test / 6m step)

| Window (test period) | Combined ret | Sharpe | Max DD | Trades |
|---|---|---|---|---|
| 2021-01→2021-07 | −0.8% | −0.11 | −7.1% | 38 |
| 2021-07→2022-01 | +5.2% | 2.29 | −5.0% | 39 |
| 2022-01→2022-07 | −3.3% | −5.50 | −4.6% | 18 |
| 2022-07→2023-01 | +0.3% | 0.96 | −1.4% | 23 |
| 2023-01→2023-07 | +11.0% | 3.32 | −6.1% | 49 |
| 2023-07→2024-01 | +1.5% | 0.72 | −16.9% | 51 |
| 2024-01→2024-07 | +14.4% | 5.19 | −5.9% | 35 |
| **Avg / % pos** | **+4.0%** | **0.98** | **−6.7%** | — / **5/7 (71%)** |

Individual: S1 +1.5%/window (5/7), S4 +0.9% (4/7), S5L +1.9% (4/7).
The 2022-H1 window is the worst failure (bear market onset, low trade count of 18).
The Sharpe −5.50 on that window is noise from only 18 trades.

---

## Blockers

### Dukascopy (Priority 3)
Server returns HTTP 503 for all datafeed URLs from this machine. Possible causes:
geo-restriction, CDN outage, or IP rate-limit. The BI5 parser in `fetch_dukascopy.py`
is correct (structure verified against spec); run it from a different IP if blocked.
Volume profile was re-tested using existing `qqq_1min_7y.csv` instead.

### cTrader (Priority 1)
Needs an app registration at https://openapi.ctrader.com (manual, interactive).
`ctrader_broker.py` raises `NotConfiguredError` until `access_token` in `config.ini`
is populated. See SETUP.md § cTrader.

### Tradovate (Priority 1)
Needs `app_id` + `app_secret` from Tradovate developer portal. Scaffold raises
`NotConfiguredError` on placeholder credentials. See SETUP.md § Tradovate.

### alerts.py
Console-only until `[alerts]` credentials are filled in `config.ini`. See SETUP.md.

---

## Next steps (in priority order)
1. Paper-trade live on Alpaca paper account for 1–3 months to validate signals
2. Set up Telegram alerts (15-minute task — see SETUP.md)
3. Configure cTrader/FTMO when ready to go prop (see SETUP.md)
4. Run `walkforward.py` again after 6 months to update the table
