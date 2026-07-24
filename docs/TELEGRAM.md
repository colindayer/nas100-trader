# TELEGRAM

Notification only. `telegram_notifier.py` cannot place, modify, or close a trade
(`test_telegram_never_places_orders`).

## Configuration
```
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_MIN_CONFIDENCE=0.5     # opportunities below this are not sent
```
Unconfigured ⇒ returns `{"sent": False, "error": ...}` and logs; never raises.

## Alert classes
`opportunity · calendar · guardian_block · promotion · shadow_result · demo_fill · live_fill ·
daily_summary · critical_error`. Unknown class is rejected (`test_telegram_rejects_unknown_class`).

## Helpers
`opportunity(o)` (confidence-filtered) · `calendar_alert(ev, minutes_out)` ·
`guardian_block(symbol, reasons)` · `promotion_change(sid, old, new)` ·
`fill(kind, symbol, side, volume, price, retcode)` · `critical(msg)` · `daily_summary(dict)`

Every send is appended to `registry/telegram_alerts.jsonl`.

**Alerts are advisory.** They are not instructions to trade manually — governance still decides.
