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
shutil.copy("/tmp/tj.jsonl", HT.DATA/"trades.jsonl")

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
