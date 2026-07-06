"""
s5_watchdog.py -- canary for the S5 ORB pillar. During a weekday 10:00-13:00 ET
breakout window the 9:00 ET opening-range bar MUST exist; if it doesn't, S5 can
never fire and the whole ORB pillar is silently dead (exactly the failure mode we
chased for days). Run hourly on the VPS; it self-gates to the window and pings
Telegram if the canary bar is missing.

Schedule (VPS):
  schtasks /create /tn "Nas100Bot-S5Watchdog" /sc HOURLY /f /tr ^
    "cmd /c cd /d <repo> && python s5_watchdog.py >> logs\\mt5_watchdog.log 2>&1"
"""
import sys
from datetime import datetime
import pytz
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

eastern = pytz.timezone("US/Eastern")
now = datetime.now(eastern)

# Only meaningful on a weekday inside the ORB breakout window (10:00-13:00 ET).
if now.weekday() >= 5 or not (10 <= now.hour < 13):
    print(f"watchdog: outside window (weekday={now.weekday()} {now.hour:02d}:00 ET) - skip")
    sys.exit(0)

from mt5_broker import MT5Broker
import alerts

try:
    b = MT5Broker()
    df = b.get_bars("QQQ", "1Hour", 12)          # QQQ -> US100
    today = now.date()
    has9 = any((ix.date() == today and ix.hour == 9) for ix in df.index)
    if has9:
        print(f"watchdog OK: 9:00 ET opening-range bar present at {now:%H:%M ET}")
    else:
        msg = (f"[S5 WATCHDOG] ALERT {now:%Y-%m-%d %H:%M ET}: 9:00 ET opening-range "
               f"bar MISSING for US100 during the breakout window -- S5 ORB cannot "
               f"fire. Check the MT5 feed / server_utc_offset in config.ini.")
        print(msg)
        alerts.send(msg)
except Exception as e:
    msg = f"[S5 WATCHDOG] ERROR {now:%H:%M ET}: {type(e).__name__}: {e}"
    print(msg)
    try:
        alerts.send(msg)
    except Exception:
        pass
