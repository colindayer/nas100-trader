"""The nightly review must diagnose causes, not just report losses."""
import sys, json, tempfile, pathlib, shutil
sys.path.insert(0,".")
import head_trader as HT

d = pathlib.Path(tempfile.mkdtemp())
(d/"data"/"challenge").mkdir(parents=True)
HT.DATA = d/"data"/"challenge"; HT.TELEM = d/"data"/"telemetry"
HT.REPORT = d/"R.md"; HT.PATCHES = d/"P.md"
# risk_audit/belief read trading_brain's OWN paths -- in production they are the same
# directory, but the test must point them at the fixture or the audit silently sees nothing.
import trading_brain as TB
TB.TRADES = HT.DATA/"trades.jsonl"; TB.BRAIN = d/"brain"; TB.EVENTS = d/"brain"/"e.jsonl"
FIXTURE = [
 {"intent_id":"i1","strategy_id":"BOT_D_gold_ny_breakout","playbook":"BREAKOUT",
  "timestamp":"2026-08-13T16:30:05+01:00","symbol":"XAUUSD","side":1,"entry":4427.42,
  "stop":4421.31,"target":4454.80,"risk_pct":0.0005,"account_equity":99944.11,"volume":0.04,
  "spread":0.5,"retcode":10009,"ticket":517571,"actual_slippage":0.02,
  "feature_snapshot":{"sl_dist":6.11},
  "market_state":{"atr20_d1":88.0,"d1_regime":"transition","d1_trend_strength_atr":2.7},
  "shadows":{"v6_wide_stop":False}},
 {"kind":"close","intent_id":"i1","strategy_id":"BOT_D_gold_ny_breakout","exit":4390.33,
  "gross":-148.36,"swap":0.0,"commission":0.0,"net":-148.36,"R":-6.07,"outcome":"stop",
  "mfe_R":0.0,"mae_R":-6.07,"holding_minutes":0,"ticket":517571},
 {"intent_id":"i2","strategy_id":"BOT_F_nas100_vwap_reversion","playbook":"REVERSION",
  "timestamp":"2026-08-13T16:07:02+01:00","symbol":"US100.cash","side":-1,"entry":30064.68,
  "stop":30159.44,"target":29924.39,"risk_pct":0.0005,"account_equity":99479.87,"volume":0.5,
  "spread":1.45,"retcode":10009,"ticket":518767,"actual_slippage":0.3,
  "feature_snapshot":{"sl_dist":94.76},
  "market_state":{"atr20_d1":633.7,"d1_regime":"transition","h4_regime":"up",
                  "d1_trend_strength_atr":2.06},
  "shadows":{"v2_range_only":False}},
 {"kind":"close","intent_id":"i2","strategy_id":"BOT_F_nas100_vwap_reversion","exit":30160.98,
  "gross":-48.15,"swap":0.0,"commission":0.0,"net":-48.15,"R":-0.97,"outcome":"stop",
  "mfe_R":0.15,"mae_R":-0.97,"holding_minutes":87,"ticket":518767},
]
(HT.DATA/"trades.jsonl").write_text(
    "\n".join(json.dumps(r) for r in FIXTURE)+"\n", encoding="utf-8")

ts = HT.merged_trades()
assert len(ts) == 2, len(ts)
by = {t["strategy_id"]: HT.diagnose(t) for t in ts}
# BOT_D: 6.11 stop on 88 ATR -> the stop, not the market
assert by["BOT_D_gold_ny_breakout"][0] == "STOP_INSIDE_NOISE", by
# BOT_F: stop was fine (15% of ATR); the cause was the 2.06 ATR extended entry
assert by["BOT_F_nas100_vwap_reversion"][0] == "EXTENDED_ENTRY", by
print(f"  BOT_D -> {by['BOT_D_gold_ny_breakout'][0]}")
print(f"  BOT_F -> {by['BOT_F_nas100_vwap_reversion'][0]} (not masked by a boundary stop)")

# a clean loss must NOT be over-diagnosed
clean = {"R":-1.0,"market_state":{"atr20_d1":88.0,"d1_regime":"range",
         "d1_trend_strength_atr":0.3},"feature_snapshot":{"sl_dist":30.0},
         "actual_slippage":0.05,"mfe_R":0.2,"mae_R":-1.0,"holding_minutes":120}
assert HT.diagnose(clean)[0] == "EXPECTED_LOSS", HT.diagnose(clean)
print(f"  ordinary loss -> EXPECTED_LOSS (no invented cause)")

# a win that nearly died must be flagged as survived, not celebrated
surv = {**clean, "R":1.8, "mae_R":-0.9}
assert HT.diagnose(surv)[0] == "SURVIVED", HT.diagnose(surv)
# missing R is UNKNOWN, never guessed
assert HT.diagnose({"R":None})[0] == "UNKNOWN"
print(f"  survived-win flagged; missing R -> UNKNOWN")

# the report must refuse a P(pass) on a tiny sample
HT.collect(None)
sys.argv = ["head_trader.py"]
try:
    HT.main()
except SystemExit:
    pass
txt = HT.REPORT.read_text()
assert "INSUFFICIENT_EVIDENCE" in txt, "computed P(pass) from 2 trades"
assert "would i deploy this desk tomorrow" in txt.lower()
assert "OBSERVATION" in txt, "risk overrun did not force OBSERVATION"
assert HT.PATCHES.exists()
print(f"  report refuses P(pass) at n=2, forces OBSERVATION, writes PATCHES.md")
print("HEAD TRADER CHECKS PASS")
