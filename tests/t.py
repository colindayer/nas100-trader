import json, shutil, tempfile, pathlib, sys
sys.path.insert(0,".")
import trading_brain as B
d = pathlib.Path(tempfile.mkdtemp())
B.BRAIN = d/"brain"; B.EVENTS = B.BRAIN/"events.jsonl"; B.TRADES = d/"trades.jsonl"
SID="BOT_A_gold_0630_breakout"
def w(rs):
    with B.TRADES.open("w") as f:
        for i,r in enumerate(rs):
            f.write(json.dumps({"intent_id":f"i{i}","strategy_id":SID,"R":r,
                "actual_slippage":0.05,"spread":0.4,"outcome":"stop" if r<0 else "target",
                "feature_snapshot":{"pre_range":8.0,"minutes_since_0630":10}})+"\n")

# no history -> neutral
w([]); assert B.recall(SID,0.15,30)["risk_multiplier"]==1.0

# 20 losses -> must SHRINK
w([-1.0]*18+[2.0]*2)
r=B.recall(SID,0.15,30); print("losing  mult",r["risk_multiplier"],"t=%.2f"%r["belief"]["t"])
assert r["risk_multiplier"]==0.5, "brain failed to derisk a losing bot"

# 45 winners -> may grow, but never past the hard cap
w([2.0]*30+[-1.0]*15)
r=B.recall(SID,0.15,30); print("winning mult",r["risk_multiplier"],"t=%.2f"%r["belief"]["t"])
assert r["risk_multiplier"]==1.5

# execution problems override an otherwise good bot
w([2.0]*30+[-1.0]*15)
ls=[json.loads(l) for l in B.TRADES.read_text().splitlines()]
for x in ls[-4:]: x["actual_slippage"]=1.2
B.TRADES.write_text("\n".join(json.dumps(x) for x in ls)+"\n")
B.learn()
r=B.recall(SID,0.15,30); print("slipping mult",r["risk_multiplier"],"execprob",r["recent_execution_problems"])
assert r["risk_multiplier"]==0.5, "brain ignored broken execution"

# append-only: learning twice must not double-count
n1=B.learn(); n2=B.learn(); assert n2==0, "brain re-learned the same trades"
print("regimes:", B.regime_table(SID))
print("ALL CHECKS PASS")
