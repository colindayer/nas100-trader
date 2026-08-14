"""reconcile() end-to-end against a stub broker. The learning loop is dead without it."""
import json, sys, tempfile, pathlib, types
sys.path.insert(0, ".")
import challenge_controller as C
import desk_events as _EV
# tests must never append to the PRODUCTION event log -- one already did,
# and its TIME_EXIT landed in the desk's real evidence and got committed.
_EV.EVENTS = pathlib.Path(tempfile.mkdtemp())/"events.jsonl"

d = pathlib.Path(tempfile.mkdtemp())
C.DATA = d; C.TRADES = d/"trades.jsonl"; C.OPEN_STATE = d/"open.json"

PRE = {"intent_id":"abc","strategy_id":"BOT_A_gold_0630_breakout","ticket":777,
       "entry":2000.0,"stop":1970.0,"target":2060.0,"side":1,"risk_pct":0.001,
       "account_equity":100000.0,"R":None,"feature_snapshot":{"sl_dist":30.0}}
C.append_trade(PRE)

class Pos:  # still open, price moved +18 then -6
    ticket=777; magic=990001; price_current=2018.0
class Deal:
    def __init__(s,p,pr,sw=0.0,cm=0.0,t=0): s.profit,s.price,s.swap,s.commission,s.time=p,pr,sw,cm,t

mt5 = types.SimpleNamespace()
mt5.positions_get = lambda **k: [Pos()]
mt5.history_deals_get = lambda **k: []
assert C.reconcile(mt5) == 0, "closed an open position"
Pos.price_current = 1994.0
C.reconcile(mt5)
st = json.loads(C.OPEN_STATE.read_text())["777"]
assert abs(st["mfe"]-18.0)<1e-9 and abs(st["mae"]+6.0)<1e-9, st
print(f"  tracking open: MFE {st['mfe']:+.1f} MAE {st['mae']:+.1f}")

# now it hits target; broker reports gross 60, swap -1.20, commission -0.80
mt5.positions_get = lambda **k: []
mt5.history_deals_get = lambda **k: [Deal(0,2000.0,0,-0.40,1000), Deal(60.0,2060.0,-1.20,-0.40,4600)]
assert C.reconcile(mt5) == 1
rows=[json.loads(l) for l in C.TRADES.read_text().splitlines()]
cl=[r for r in rows if r.get("kind")=="close"][0]
assert cl["outcome"]=="target", cl["outcome"]
assert abs(cl["net"]-58.0)<1e-9, cl["net"]           # net is AFTER swap+commission
assert abs(cl["R"]-0.58)<1e-9, cl["R"]              # R on 100 risked, net not gross
assert abs(cl["mfe_R"]-0.6)<1e-9 and abs(cl["mae_R"]+0.2)<1e-9
assert cl["holding_minutes"]==60
print(f"  closed: R {cl['R']:+.3f} net {cl['net']:+.2f} (gross {cl['gross']:+.1f}) "
      f"MFE {cl['mfe_R']:+.2f}R MAE {cl['mae_R']:+.2f}R hold {cl['holding_minutes']}m")

assert C.reconcile(mt5) == 0, "closed the same trade twice"
assert len([r for r in rows if r.get("kind")!="close"])==1, "overwrote the pre-trade row"

# the Brain must now see it
import trading_brain as B
B.TRADES = C.TRADES; B.BRAIN=d/"b"; B.EVENTS=B.BRAIN/"e.jsonl"
ct = B.closed_trades()
assert len(ct)==1 and abs(ct[0]["R"]-0.58)<1e-9
assert ct[0]["entry"]==2000.0, "lost the pre-trade context on merge"
B.learn(); assert len(B.events("trade_learned"))==1
print(f"  brain merged: entry {ct[0]['entry']} + R {ct[0]['R']:+.3f}")
print("RECONCILE CHECKS PASS")
