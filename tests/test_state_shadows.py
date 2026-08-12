"""Market state must not look forward. Shadows must not flatter themselves."""
import sys, json, tempfile, pathlib
import pandas as pd, numpy as np
sys.path.insert(0,".")
import market_state as MS, shadows as SH

# ---------- lookahead: the forming bar must be invisible ----------
NOW = None
class FakeMT5:
    TIMEFRAME_D1=1; TIMEFRAME_H4=2; TIMEFRAME_H1=3
    TIMEFRAME_M15=4; TIMEFRAME_M5=5; TIMEFRAME_M1=6
    def __init__(self, spike): self.spike=spike
    def copy_rates_from_pos(self, sym, tf, start, n):
        per = {1:"1D",2:"4h",3:"1h",4:"15min",5:"5min",6:"1min"}[tf]
        # grid offset by half a period so one bar genuinely STRADDLES `now`:
        # it opened in the past and has not closed yet. That is the real forming bar.
        end = NOW + pd.Timedelta(per) / 2
        idx = pd.date_range(end=end.tz_convert("UTC"), periods=n, freq=per)
        d = pd.DataFrame({"time":(idx.astype("int64")//10**9),
                          "open":100.0,"high":101.0,"low":99.0,"close":100.0,"tick_volume":5})
        if self.spike:
            d.iloc[-1, d.columns.get_loc("high")] = 9999.0   # future bar
            d.iloc[-2, d.columns.get_loc("high")] = 9999.0   # the FORMING bar
        return d.to_records(index=False)

NOW = pd.Timestamp("2026-08-12 14:37", tz="Europe/London")
now = NOW
clean = MS.compute(FakeMT5(False), "X", now, 100.0, 0.2)
spiked = MS.compute(FakeMT5(True),  "X", now, 100.0, 0.2)
leaked = [k for k in clean if isinstance(clean.get(k),(int,float))
          and clean.get(k) != spiked.get(k)]
assert not leaked, f"LOOKAHEAD: forming bar changed {leaked[:6]}"
print(f"  no lookahead: {len(clean)} fields identical with a 9999 spike on the forming bar")
assert clean.get("atr20_d1") and "ms_labels" in clean
print(f"  labels: {clean['ms_labels']}")

# ---------- shadows: None must never count as a skip ----------
st = {"d1_above_sma20": None, "room_above_atr": 2.0, "vol_expansion": 1.4,
      "bq_break_type": "clean", "atr20_d1": 60.0, "d1_trend_strength_atr": 0.5}
v = SH.evaluate("BOT_A_gold_0630_breakout", st, side=1, sl_dist=30.0)
assert v["v2_trend_align"] is None, "unevaluable variant returned a verdict"
assert v["v3_htf_room"] is True and v["v6_wide_stop"] is True
assert v["v5_clean_break"] is True
print(f"  shadow verdicts: {v}")

# BOT_D's real trade: 6.11pt stop, gold ATR ~60 -> v6 must say SKIP
bad = SH.evaluate("BOT_D_gold_ny_breakout", {**st}, side=1, sl_dist=6.11)
assert bad["v6_wide_stop"] is False, "wide-stop shadow approved a 6.11pt gold stop"
print("  v6_wide_stop correctly rejects BOT_D's 6.11pt stop (needs 15.0)")

# ---------- scoreboard arithmetic ----------
trades = [
    {"strategy_id":"B","R": 2.0,"shadows":{"v2":True,"v3":None}},
    {"strategy_id":"B","R":-1.0,"shadows":{"v2":False,"v3":None}},
    {"strategy_id":"B","R":-1.0,"shadows":{"v2":False,"v3":None}},
    {"strategy_id":"B","R": 1.0,"shadows":{"v2":True,"v3":None}},
]
sb = SH.scoreboard(trades)["B::v2"]
assert sb["n_taken"]==2 and sb["n_skipped"]==2
assert abs(sb["exp_taken"]-1.5)<1e-9 and abs(sb["exp_skipped"]+1.0)<1e-9
assert abs(sb["delta_vs_live"]-1.25)<1e-9      # 1.5 vs live 0.25
u = SH.scoreboard(trades)["B::v3"]
assert u["n_taken"]==0 and u["n_unevaluable"]==4, "unevaluable variant looked selective"
print(f"  v2: taken {sb['n_taken']} exp {sb['exp_taken']:+.2f} vs live +0.25 "
      f"(delta {sb['delta_vs_live']:+.2f}); v3 unevaluable on all 4, not credited")
print("STATE + SHADOW CHECKS PASS")
