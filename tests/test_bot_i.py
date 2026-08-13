"""BOT_I: seven conditions, in order, on closed bars only. And it must never send."""
import sys; sys.path.insert(0,".")
import pandas as pd, numpy as np
from bot_i import AsianSweepLondonReversal

b = AsianSweepLondonReversal()
DAY = pd.Timestamp("2026-08-14", tz="Europe/London")
ATR = 88.0
STATE = {"atr20_d1": ATR, "lvl_prev_day_low": 4300.0, "lvl_prev_day_high": 4500.0}

def session(london_bars):
    """Asia 00:00-07:00 flat 4390-4410, then the London bars supplied."""
    ai = pd.date_range(DAY, DAY + pd.Timedelta(hours=7) - pd.Timedelta(minutes=1),
                       freq="1min", tz="Europe/London")
    asia = pd.DataFrame({"open":4400.0,"high":4410.0,"low":4390.0,"close":4400.0,
                         "tick_volume":5}, index=ai)
    li = pd.date_range(DAY + pd.Timedelta(hours=7), periods=len(london_bars),
                       freq="1min", tz="Europe/London")
    lon = pd.DataFrame(london_bars, index=li)
    return pd.concat([asia, lon])

def bar(o,h,l,c): return {"open":o,"high":h,"low":l,"close":c,"tick_volume":5}

# a full valid sequence: sweep 4410 -> reject -> bearish displacement -> break low -> origin -> retest
# NOTE: the quiet bars must VARY. Flat identical lows can never form a fractal swing, so the
# bot correctly refused the first version of this fixture -- there was no structure to break.
bars = [bar(4400,4402,4398,4400),
        bar(4400,4401,4396,4398),
        bar(4398,4399,4394,4396),                          # <- swing low 4394 (2 each side)
        bar(4396,4399,4396,4398),
        bar(4398,4402,4397,4401),
        bar(4401,4404,4400,4403),
        bar(4403,4406,4402,4405)]
bars += [bar(4405,4425,4404,4420)]                        # SWEEP high (+0.17 ATR)
bars += [bar(4420,4421,4405,4408)]                        # REJECTION back inside
bars += [bar(4408,4412,4406,4411)]                        # ORIGIN: last bullish candle
bars += [bar(4411,4412,4385,4388)]                        # DISPLACEMENT body 23 = .26 ATR
bars += [bar(4388,4390,4380,4382)]*3                      # breaks the 4394 swing low
bars += [bar(4382,4412,4381,4386)]                        # retest into origin, 84% upper wick
d = session(bars)
now = d.index[-1] + pd.Timedelta(minutes=1)
sig = b.generate_signal({"now_london":now,"state":STATE,"m1":d,
                         "bid":4410.0,"ask":4410.5,"traded_today":{}})
assert sig is not None, f"valid sequence rejected: {b.no_signal_reason}"
assert sig.side == -1, sig.side
fs = sig.feature_snapshot
assert sig.stop_price > 4425.0, sig.stop_price          # stop beyond the SWEEP, structural
assert abs(sig.target_price - 4390.0) < 1e-6, sig.target_price   # TP2 = Asia low
print(f"  full sequence -> SHORT entry {sig.entry_price} stop {sig.stop_price:.2f} "
      f"tp2 {sig.target_price}")
for k in ("sweep_size_atr","rejection_speed_bars","displacement_size_atr",
          "structure_break_dist_atr","retracement_depth","origin_wick_ratio",
          "entry_delay_bars","tp1_internal","tp2_asia_opposite","tp3_htf"):
    assert k in fs, f"missing measurement {k}"
print(f"  measurements: sweep {fs['sweep_size_atr']:.2f}atr, reject in "
      f"{fs['rejection_speed_bars']} bars, disp {fs['displacement_size_atr']:.2f}atr, "
      f"wick {fs['origin_wick_ratio']:.0%}")

# --- each condition must be REQUIRED ---
def run(bb, bid=4410.0, ask=4410.5):
    dd = session(bb); n = dd.index[-1] + pd.Timedelta(minutes=1)
    return b.generate_signal({"now_london":n,"state":STATE,"m1":dd,
                              "bid":bid,"ask":ask,"traded_today":{}})

# no sweep at all
assert run([bar(4400,4402,4398,4400), bar(4400,4401,4396,4398),
            bar(4398,4399,4394,4396)]*7) is None and "no sweep" in b.no_signal_reason
print(f"  no sweep -> {b.no_signal_reason[:44]}")

# swept but ACCEPTED outside (never closes back in) -> breakout, not a sweep
accept = bars[:7] + [bar(4405,4425,4404,4420)] + [bar(4420,4440,4418,4435)]*25
assert run(accept, bid=4435, ask=4435.5) is None
assert "never closed back inside" in b.no_signal_reason or "acceptance" in b.no_signal_reason
print(f"  acceptance outside -> {b.no_signal_reason[:50]}")

# rejected but the down-move is a weak candle, not displacement
weak = (bars[:7] + [bar(4405,4425,4404,4420)] +
        [bar(4420,4421,4405,4408)] + [bar(4408,4410,4404,4406)]*10)
assert run(weak, bid=4406, ask=4406.5) is None and "displacement" in b.no_signal_reason
print(f"  weak candle -> {b.no_signal_reason[:48]}")

# displacement present but price never returns to the origin -> no chasing
nochase = bars[:-1] + [bar(4382,4384,4380,4381)]
assert run(nochase, bid=4381, ask=4381.5) is None and "no retest" in b.no_signal_reason
print(f"  no retest -> {b.no_signal_reason[:44]} (never chases)")

# back at the origin but with no rejection wick
nowick = bars[:-1] + [bar(4405,4412,4404,4411)]
assert run(nowick, bid=4410.0, ask=4410.5) is None and "no rejection at origin" in b.no_signal_reason
print(f"  no rejection wick -> {b.no_signal_reason[:46]}")

# --- determinism: same closed bars, same answer ---
s2 = run(bars)
assert s2 is not None and s2.entry_price == sig.entry_price and s2.stop_price == sig.stop_price
print("  deterministic: identical signal on re-evaluation (no repainting)")

# --- it must be a shadow ---
assert b.shadow is True and b.stage == "SHADOW"
assert b.risk_override == 0.0005
import desk as D
assert D.eligibility(b, ["TRANSITION","AT_HTF_LEVEL"])[0]
assert not D.eligibility(b, ["STRONG_TREND"])[0], "sweep reversal allowed in a strong trend"
print(f"  SHADOW, 0.05% when promoted, blocked from STRONG_TREND")
print("BOT_I CHECKS PASS")
