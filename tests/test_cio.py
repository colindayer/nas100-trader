"""The CIO ranks and decides. It never freezes because the match is imperfect."""
import sys; sys.path.insert(0,".")
import desk as D
from challenge_controller import BOTS
class CS:
    def __init__(s, v=None): s.v = v
    def veto(s, r): return s.v

# ---- 2026-08-13's REAL state, which froze the previous CIO at 0.000%
real = {"EURUSD":{"opportunities":["WEAK_TREND","COMPRESSION","AT_HTF_LEVEL","RISK_ON"]},
        "US100.cash":{"opportunities":["TRANSITION","COMPRESSION","EXTENDED","AT_HTF_LEVEL","RISK_ON"]},
        "US500.cash":{"opportunities":["WEAK_TREND","COMPRESSION","EXTENDED","AT_HTF_LEVEL","RISK_ON"]},
        "XAUUSD":{"opportunities":["TRANSITION","EXTENDED","AT_HTF_LEVEL","RISK_ON"]}}
p = D.allocate(BOTS, real, lambda b: b.risk_override or 0.0010, CS())
assert p["total_risk"] > 0, "CIO froze on the real market again"
print(f"  2026-08-13 real state -> {p['total_risk']:.3%} allocated (was 0.000%)")

# ---- nothing fits ANY specialist (UNKNOWN is the real gap): still probe exactly one
live = [b for b in BOTS if not getattr(b, "shadow", False)]
nofit = {b.symbol: {"opportunities":["UNKNOWN","EXTENDED","COMPRESSION"]} for b in BOTS}
p2 = D.allocate(live, nofit, lambda b: b.risk_override or 0.0010, CS())
funded = [s for s,d in p2["decisions"].items() if d["allow"]]
assert len(funded) == 1, f"expected one probe, got {funded}"
assert p2["total_risk"] == D.MIN_EXPERIMENTAL_RISK, p2["total_risk"]
print(f"  no specialist fits -> probes {funded[0]} at {p2['total_risk']:.3%}")

# a SHADOW must never consume the risk budget it does not use
sh = [b for b in BOTS if getattr(b, "shadow", False)]
assert sh, "no shadow bot registered"
allfit = {b.symbol: {"opportunities":["TRANSITION","AT_HTF_LEVEL"]} for b in BOTS}
p2b = D.allocate(BOTS, allfit, lambda b: b.risk_override or 0.0010, CS())
p2c = D.allocate(live, allfit, lambda b: b.risk_override or 0.0010, CS())
assert p2b["total_risk"] == p2c["total_risk"], "shadow consumed the risk budget"
assert p2b["decisions"][sh[0].strategy_id]["shadow"] is True
print(f"  shadow {sh[0].strategy_id.split('_')[1]} ranked and recorded, "
      f"budget unchanged at {p2b['total_risk']:.3%}")

# ---- modifiers must NEVER hard-block; only regimes do
a = next(b for b in BOTS if b.strategy_id=="BOT_A_gold_0630_breakout")
assert D.eligibility(a, ["WEAK_TREND","EXTENDED","COMPRESSION"])[0], "modifier blocked a bot"
u = D.utility(a, ["WEAK_TREND","EXTENDED","COMPRESSION"])
assert u["score"] < D.utility(a, ["WEAK_TREND"])["score"], "modifiers did not penalise"
print(f"  modifiers penalise not veto: {u['score']} vs "
      f"{D.utility(a,['WEAK_TREND'])['score']} clean")

# ---- but a WRONG REGIME is still an absolute block (BOT_F's live mistake)
f = next(b for b in BOTS if b.strategy_id=="BOT_F_nas100_vwap_reversion")
assert not D.eligibility(f, ["TRANSITION","EXTENDED"])[0], "fade bot allowed into a transition"
assert not D.eligibility(f, ["STRONG_TREND"])[0]
print("  BOT_F still hard-blocked from TRANSITION and STRONG_TREND")

# ---- Risk Manager veto is absolute and outranks utility
p3 = D.allocate(BOTS, real, lambda b: 0.0010, CS("daily headroom too thin"))
assert p3["total_risk"] == 0.0, "risk veto ignored"
assert all("RISK MANAGER" in d["reason"] for d in p3["decisions"].values() if not d["allow"]
           and "structurally" not in d["reason"] and "outranked" not in d["reason"])
print("  Risk Manager veto -> 0.000%, and it says who stopped it")

# ---- coverage reports gaps only for REGIMES, not modifiers
cov = D.coverage(BOTS, ["WEAK_TREND","RISK_ON","EXTENDED","AT_HTF_LEVEL","RANGE"])
assert "RISK_ON" not in cov["gaps"] and "EXTENDED" not in cov["gaps"], cov["gaps"]
assert set(cov["covered"]) <= D.REGIMES
print(f"  coverage gaps now regimes only: {cov['gaps']}")
print("CIO CHECKS PASS")
