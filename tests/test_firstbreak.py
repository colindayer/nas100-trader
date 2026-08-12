"""The live bot must take the FIRST break only -- same as the frozen backtest."""
import sys, pandas as pd, numpy as np
sys.path.insert(0,".")
from challenge_controller import GoldBreakout0630

def bars(day, upto_h, upto_m, spike_at=None, spike=0.0):
    idx = pd.date_range(f"{day} 04:00", f"{day} {upto_h:02d}:{upto_m:02d}", freq="1min",
                        tz="Europe/London")
    df = pd.DataFrame({"open":100.0,"high":100.5,"low":99.5,"close":100.0,
                       "tick_volume":10}, index=idx)
    df.loc[df.index < f"{day} 06:30", ["high","low"]] = [101.0, 99.0]   # pre-range 99..101
    if spike_at:
        df.loc[f"{day} {spike_at}", "high"] = spike
    return df

D="2026-08-12"
b = GoldBreakout0630()
# price ABOVE the level right now, and it already broke at 06:35 -> must refuse
df = bars(D, 8, 12, spike_at="06:35", spike=101.5)
ctx = {"now_london": df.index[-1], "m1": df, "bid": 101.4, "ask": 101.5, "traded_today": {}}
assert b.generate_signal(ctx) is None, "chased a re-test hours after the first break"
assert "first break already happened at 06:35" in b.no_signal_reason, b.no_signal_reason
print("  late re-entry refused:", b.no_signal_reason)

# genuine first break happening now -> must trade
df2 = bars(D, 6, 40)
ctx2 = {"now_london": df2.index[-1], "m1": df2, "bid": 101.4, "ask": 101.5, "traded_today": {}}
s = b.generate_signal(ctx2)
assert s is not None and s.side == 1, f"refused a genuine first break: {b.no_signal_reason}"
assert abs(s.stop_price - (s.entry_price-30)) < 1e-9
print(f"  first break taken: entry {s.entry_price} stop {s.stop_price} target {s.target_price}")
print("FIRST-BREAK CHECKS PASS")
