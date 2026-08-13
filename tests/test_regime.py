"""'mixed' was the fallback for 'detected nothing'. A gate built on it approved a
2-ATR-extended fade. A range must be POSITIVELY identified."""
import sys; sys.path.insert(0,".")
import market_state as MS, shadows as SH

R = MS._regime
# today's real US100: price 2.02 ATR above a rising SMA20
# a V-recovery: 2 ATR above the mean, but the 20d mean has barely moved (slope 0.0175%).
# Not a range, and NOT an established uptrend either -- "transition" is the honest label.
assert R(30100.88, 28818.0, 29299.0, 633.749, 0.000175) == "transition"
# genuine range: price hugging a flat mean
assert R(100.0, 100.2, 105.0, 5.0, 0.00001) == "range"
# far from the mean but the mean is flat -> NOT a range
assert R(115.0, 100.0, 105.0, 5.0, 0.00001) == "transition"
# clean downtrend
assert R(90.0, 95.0, 98.0, 5.0, -0.002) == "down"
assert R(110.0, 105.0, 100.0, 5.0, 0.002) == "up"          # mean genuinely rising
# no data -> unknown, never silently 'range'
assert R(100.0, None, None, None, None) == "unknown"
print("  regime: up / range / transition / down / unknown all distinct")

# labels must be mutually exclusive -- engine emitted TREND_UP and RANGE together
for reg, want in (("up","TREND_UP"), ("down","TREND_DOWN"),
                  ("range","RANGE"), ("transition","TRANSITION")):
    L = MS.classify({"d1_regime": reg, "d1_trend_strength_atr": 0.5})
    trend_labels = [x for x in L if x in ("TREND_UP","TREND_DOWN","RANGE","TRANSITION")]
    assert trend_labels == [want], f"{reg} -> {L}"
assert "EXTENDED" in MS.classify({"d1_regime":"up","d1_trend_strength_atr":2.02})
print("  labels mutually exclusive; EXTENDED fires at 2.02 ATR")

# the gate that matters: today's fade must be recorded as SKIP
today = {"d1_regime":"up","d1_trend_strength_atr":2.024,"room_below_atr":0.231,
         "vol_expansion":0.584,"atr20_d1":633.749}
v = SH.evaluate("BOT_F_nas100_vwap_reversion", today, side=-1, sl_dist=95.06)
assert v["v2_range_only"] is False and v["v5_not_extended"] is False
# and a real range day must be allowed through
calm = {"d1_regime":"range","d1_trend_strength_atr":0.3,"room_below_atr":1.2,
        "vol_expansion":0.9,"atr20_d1":633.749}
v2 = SH.evaluate("BOT_F_nas100_vwap_reversion", calm, side=-1, sl_dist=200.0)
assert v2["v2_range_only"] is True and v2["v5_not_extended"] is True
print("  BOT_F: trending fade SKIP, ranging fade TAKE")
print("REGIME CHECKS PASS")
