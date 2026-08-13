"""BOT_H must require a level to FAIL: pierce, then reclaim, promptly."""
import sys; sys.path.insert(0,".")
import pandas as pd
from challenge_controller import LiquiditySweepReclaim
import desk as D

b = LiquiditySweepReclaim()
NOW = pd.Timestamp("2026-08-13 12:00", tz="Europe/London")
STATE = {"atr20_d1": 88.0, "lvl_prev_day_high": 4400.0, "lvl_prev_day_low": 4300.0}

def bars(highs, lows, closes):
    idx = pd.date_range(end=NOW - pd.Timedelta(minutes=1), periods=len(highs), freq="1min",
                        tz="Europe/London")
    return pd.DataFrame({"open":closes,"high":highs,"low":lows,"close":closes,
                         "tick_volume":5}, index=idx)

n = 20
# 1. clean sweep above prev-day-high (4400) then close back below -> SHORT
h = [4390.0]*n; h[-5] = 4410.0                    # pierced 10 = 0.11 ATR
c = [4390.0]*n
sig = b.generate_signal({"now_london":NOW,"state":STATE,"m1":bars(h,[4380.0]*n,c),
                         "bid":4389.5,"ask":4390.0,"traded_today":{}})
assert sig is not None and sig.side == -1, b.no_signal_reason
assert sig.stop_price > 4410.0, sig.stop_price       # stop beyond the sweep extreme
print(f"  sweep above 4400 -> SHORT entry {sig.entry_price} stop {sig.stop_price:.2f} "
      f"target {sig.target_price:.2f}")

# 2. price pierced but did NOT reclaim (still above) -> no trade
c2 = [4390.0]*n; c2[-1] = 4405.0
r = b.generate_signal({"now_london":NOW,"state":STATE,"m1":bars(h,[4380.0]*n,c2),
                       "bid":4404.5,"ask":4405.0,"traded_today":{}})
assert r is None and "swept and reclaimed" in b.no_signal_reason
print(f"  pierced but not reclaimed -> no trade")

# 3. a touch, not a pierce -> no trade
h3 = [4390.0]*n; h3[-5] = 4400.5                  # 0.006 ATR, below MIN_PIERCE_ATR
r = b.generate_signal({"now_london":NOW,"state":STATE,"m1":bars(h3,[4380.0]*n,c),
                       "bid":4389.5,"ask":4390.0,"traded_today":{}})
assert r is None, "traded a touch as though it were a sweep"
print(f"  touched but did not pierce -> no trade")

# 4. sweep BELOW prev-day-low then reclaim -> LONG
l = [4310.0]*n; l[-5] = 4290.0
c4 = [4310.0]*n
sig4 = b.generate_signal({"now_london":NOW,"state":STATE,"m1":bars([4320.0]*n,l,c4),
                          "bid":4310.0,"ask":4310.5,"traded_today":{}})
assert sig4 is not None and sig4.side == 1, b.no_signal_reason
assert sig4.stop_price < 4290.0
print(f"  sweep below 4300 -> LONG stop {sig4.stop_price:.2f} (beyond the low)")

# 5. stale sweep outside the reclaim window -> no trade
h5 = [4390.0]*40; h5[0] = 4410.0
idx = pd.date_range(end=NOW - pd.Timedelta(minutes=1), periods=40, freq="1min",
                    tz="Europe/London")
stale = pd.DataFrame({"open":4390.0,"high":h5,"low":4380.0,"close":4390.0,
                      "tick_volume":5}, index=idx)
r = b.generate_signal({"now_london":NOW,"state":STATE,"m1":stale,"bid":4389.5,
                       "ask":4390.0,"traded_today":{}})
assert r is None, "faded a 40-minute-old sweep"
print(f"  sweep older than the reclaim window -> no trade")

# 6. the desk allocates it exactly where the gap was
gap = {"XAUUSD": {"opportunities":["TRANSITION","EXTENDED","AT_HTF_LEVEL","RISK_ON"]}}
assert D.eligibility(b, gap["XAUUSD"]["opportunities"])[0]
u = D.utility(b, gap["XAUUSD"]["opportunities"])
assert u["fit"] == 1.0, u
assert not D.eligibility(b, ["STRONG_TREND"])[0], "sweep bot allowed into a strong trend"
print(f"  TRANSITION+AT_HTF_LEVEL -> fit {u['fit']}, score {u['score']}")
cov = D.coverage([b], ["TRANSITION"])
assert not cov["gaps"], cov
print(f"  TRANSITION gap now covered")
print("SWEEP CHECKS PASS")
