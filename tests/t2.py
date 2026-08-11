import json,sys,tempfile,pathlib,types
sys.path.insert(0,".")
import trading_brain as B
d=pathlib.Path(tempfile.mkdtemp()); B.BRAIN=d/"b"; B.EVENTS=B.BRAIN/"e.jsonl"; B.TRADES=d/"t.jsonl"
def mk(sid,rs,rng,spr,sl,slip,tag=""):
    with B.TRADES.open("a") as f:
        for i,r in enumerate(rs):
            f.write(json.dumps({"intent_id":f"{sid}{tag}{i}","strategy_id":sid,"R":r,"spread":spr,
              "actual_slippage":slip,"outcome":"x",
              "feature_snapshot":{"pre_range":rng*(1+0.5*(i%2)),"sl_dist":sl,"minutes_since_entry":5*(i%12)}})+"\n")
A="BOT_A_gold_0630_breakout"; Bb="BOT_B_nas100_usopen_breakout"
mk(A,[1,-1]*10, 10.0, 0.40, 30.0, 0.05)
mk(Bb,[1,-1]*10, 120.0, 3.0, 60.0, 2.0)   # 2.0 pts slip on a 60-pt stop = 3.3%, FINE
B.learn()
la={e["strategy_id"]:[] for e in B.events("trade_learned")}
for e in B.events("trade_learned"): la[e["strategy_id"]].append(e["lesson"])
assert "EXECUTION_PROBLEM" not in la[Bb], "index slippage wrongly flagged"
print("B lessons ok, regimes A:",list(B.regime_table(A)),"| B:",list(B.regime_table(Bb)))
# now genuinely bad index slippage: 12 pts on 60-pt stop
mk(Bb,[-1]*5, 120.0, 3.0, 60.0, 12.0, "slip"); B.learn()
last=[e["lesson"] for e in B.events("trade_learned") if e["strategy_id"]==Bb][-5:]
assert "EXECUTION_PROBLEM" in last, "real index slippage missed"
r=B.recall(Bb,0.0,10); print("B mult",r["risk_multiplier"],"execprob",r["recent_execution_problems"])
assert r["risk_multiplier"]==0.5
print("relative-scale checks PASS")
