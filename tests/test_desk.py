"""The desk allocates. Bots never allocate themselves."""
import sys; sys.path.insert(0,".")
import desk as D
from challenge_controller import BOTS

# ---- classification is a READING of state, not a prediction
today = {"d1_regime":"transition","h4_regime":"up","d1_trend_strength_atr":2.024,
         "vol_expansion":0.584,"room_below_atr":0.231,"macro_risk":"RISK_ON"}
o = D.classify_opportunity(today)["opportunities"]
assert set(o) == {"TRANSITION","COMPRESSION","EXTENDED","AT_HTF_LEVEL","RISK_ON"}, o
print(f"  2026-08-13 US100 -> {o}")

# ---- BOT_F must NOT be allocated this market (it shorted into it live)
byid = {b.strategy_id: b for b in BOTS}
ok, why = D.eligibility(byid["BOT_F_nas100_vwap_reversion"], o)
assert not ok, "reversion bot allocated a transition/extended market"
print(f"  BOT_F: NOT ALLOCATED -- {why}")

# ---- breakout bots also stand down: compression is not breakout weather
ok, why = D.eligibility(byid["BOT_B_nas100_usopen_breakout"], o)
assert not ok, why
print(f"  BOT_B: NOT ALLOCATED -- {why}")

# ---- a genuine range: the fade bot IS allocated, breakouts are not
rng = {"d1_regime":"range","h4_regime":"range","vol_expansion":0.9,
       "d1_trend_strength_atr":0.2}
ro = D.classify_opportunity(rng)["opportunities"]
assert D.eligibility(byid["BOT_F_nas100_vwap_reversion"], ro)[0]
assert not D.eligibility(byid["BOT_A_gold_0630_breakout"], ro)[0]
print(f"  range {ro} -> BOT_F allocated, BOT_A stands down")

# ---- confirmed trend: only the continuation specialist
tr = {"d1_regime":"up","h4_regime":"up","vol_expansion":1.3,"d1_trend_strength_atr":1.0}
to = D.classify_opportunity(tr)["opportunities"]
assert "STRONG_TREND" in to and "EXPANSION" in to
allowed = [b.strategy_id for b in BOTS if D.eligibility(b, to)[0]]
assert "BOT_G_nas100_h4_pullback" in allowed, allowed
assert "BOT_F_nas100_vwap_reversion" not in allowed
print(f"  strong trend -> {allowed}")

# ---- the group cap: 5 breakout bots are ONE bet
class CS:
    def veto(self, r): return None
trend_by_sym = {b.symbol: {"opportunities": to} for b in BOTS}
a = D.allocate(BOTS, trend_by_sym, lambda b: 0.0010, CS(), group_cap=0.0015)
brk = [s for s,d in a["decisions"].items() if d["allow"] and d.get("group")=="BREAKOUT"]
assert len(brk) == 1, f"group cap let {len(brk)} correlated bots through"
assert a["group_used"].get("BREAKOUT", 0) <= 0.0015
print(f"  breakout group capped: {len(brk)} of 5 allocated, group at "
      f"{a['group_used'].get('BREAKOUT',0):.3%}")
assert a["total_risk"] <= 0.0075

# ---- coverage gap is visible with zero evidence
cov = D.coverage(BOTS, sorted(D.REGIMES))
for r in ("STRONG_TREND", "WEAK_TREND", "RANGE", "TRANSITION"):
    assert cov["covered"][r], f"no specialist for {r}"
# UNKNOWN stays an honest gap: nothing should claim to specialise in an unreadable market
assert cov["gaps"] == ["UNKNOWN"], cov["gaps"]
print(f"  every readable regime covered; remaining gap: {cov['gaps']}")

# ---- the CIO refuses to rank on five trades
r = D.state_conditional_edge([{"strategy_id":"BOT_A","R":-1.0,"market_state":today}]*5,
                             "TRANSITION")
assert r["status"] == "INSUFFICIENT_EVIDENCE" and r["n"] == 5 and r["need"] == 30
print(f"  state-conditional edge: {r['status']} ({r['n']}/{r['need']}) -- refuses to guess")
print("DESK CHECKS PASS")
