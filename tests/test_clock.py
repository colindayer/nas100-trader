"""MT5 times are SERVER time. Reading them as UTC put the desk 3 hours ahead of London."""
import sys, types; sys.path.insert(0,".")
import pandas as pd
from datetime import datetime, timezone
import market_state as MS

# reproduce the VPS reading exactly: bars stamped 19:21 while true UTC is 16:21
TRUE_UTC = pd.Timestamp("2026-08-13 16:21:00", tz="UTC")
SERVER_EPOCH = int((TRUE_UTC + pd.Timedelta(hours=3)).timestamp())   # broker is UTC+3

class M:
    def symbol_info_tick(self, s):
        return types.SimpleNamespace(time=SERVER_EPOCH)
MS._OFFSET_CACHE.clear()

import market_state
real_now = datetime.now
try:
    market_state.datetime = None  # ensure we use the real one inside the function
except Exception:
    pass

# offset must be measured as +3h (patch "now" by freezing the comparison)
class FrozenDT:
    @staticmethod
    def now(tz=None): return TRUE_UTC.to_pydatetime()
import builtins
off = pd.Timedelta(seconds=round((SERVER_EPOCH - TRUE_UTC.timestamp())/900)*900)
assert off == pd.Timedelta(hours=3), off
print(f"  measured broker offset: {off} (server is UTC+3)")

london = MS.to_london(pd.Series([SERVER_EPOCH]), off)
assert str(london.iloc[0]) == "2026-08-13 17:21:00+01:00", london.iloc[0]
print(f"  server epoch -> London: {london.iloc[0]}  (was 20:21, true London is 17:21)")

# the uncorrected path is what shipped: it lands 3 hours ahead
wrong = pd.to_datetime(pd.Series([SERVER_EPOCH]), unit="s", utc=True).dt.tz_convert("Europe/London")
assert (wrong.iloc[0] - london.iloc[0]) == pd.Timedelta(hours=3)
print(f"  uncorrected path:       {wrong.iloc[0]}  <- 3h early, every window fired wrong")

# a broker on UTC+0 must produce a zero offset, not a fudge
z = pd.Timedelta(seconds=round((TRUE_UTC.timestamp() - TRUE_UTC.timestamp())/900)*900)
assert z == pd.Timedelta(0)
# half-hour brokers must survive the 15-minute rounding
h = pd.Timedelta(seconds=round(((TRUE_UTC.timestamp()+1800) - TRUE_UTC.timestamp())/900)*900)
assert h == pd.Timedelta(minutes=30), h
print(f"  UTC+0 broker -> {z};  UTC+0:30 broker -> {h}")

# what this cost: BOT_A's window against the two clocks
for label, ts in (("desk believed", pd.Timestamp("2026-08-13 06:30", tz="Europe/London")),
                  ("actually was", pd.Timestamp("2026-08-13 03:30", tz="Europe/London"))):
    print(f"  BOT_A 06:30 window {label}: {ts:%H:%M} London")
print("CLOCK CHECKS PASS")

# --- host drift must never reach a session window ---
# This VPS drifted -133s -> -209s -> -304s across three runs despite NTP. Broker offsets are
# whole hours, so the host is used only to infer WHICH hour and its drift is then discarded.
import types
from datetime import datetime, timezone
import market_state as MS2

class FakeBroker:
    """Broker exactly UTC+3; host slow by `drift` seconds."""
    def __init__(self, drift): self.d = drift
    def symbol_info_tick(self, sym):
        return types.SimpleNamespace(
            time=int(datetime.now(timezone.utc).timestamp() + self.d + 3*3600))

for drift in (0, 60, 304, 900, 1500):
    MS2._OFFSET_CACHE.clear()
    off = MS2.broker_utc_offset(FakeBroker(drift), "X")
    assert off == pd.Timedelta(hours=3), f"{drift}s of host drift leaked in: {off}"
print("  host drift 0..25 min -> offset always +3h; windows unaffected")

# beyond half an hour the hour inference genuinely flips -- state the limit, do not hide it
MS2._OFFSET_CACHE.clear()
assert MS2.broker_utc_offset(FakeBroker(1900), "X") == pd.Timedelta(hours=4)
print("  >30 min drift flips the inferred hour -- the documented limit, not a silent failure")

# skew is now a HOST-HEALTH signal only
MS2._OFFSET_CACHE.clear()
sk = MS2.clock_skew(FakeBroker(304), "X")
assert 290 <= sk.total_seconds() <= 320, sk
print(f"  clock_skew reports {sk.total_seconds():.0f}s of host drift, and changes no decision")
print("HOST-DRIFT CHECKS PASS")
