"""Time exits: close only what can be PROVEN ours. BOT_A held gold 23h without this."""
import sys, types, json, tempfile, pathlib
import pandas as pd
sys.path.insert(0,".")
import challenge_controller as C
from challenge_controller import GoldBreakout0630, IndexBreakoutUSOpen

d = pathlib.Path(tempfile.mkdtemp()); C.DATA = d; C.TRADES = d/"t.jsonl"
YDAY = (pd.Timestamp.now(tz="Europe/London") - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=10)
C.append_trade({"intent_id":"a1","strategy_id":"BOT_A_gold_0630_breakout","symbol":"XAUUSD",
                "ticket":777,"timestamp":YDAY.isoformat(),"entry":4404.52})

class P:
    def __init__(s,tk,sym,mg=990001,typ=0): s.ticket,s.symbol,s.magic,s.type,s.volume=tk,sym,mg,typ,0.03
sent=[]
mt5 = types.SimpleNamespace(
    TRADE_ACTION_DEAL=1, ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1,
    ORDER_TIME_GTC=0, ORDER_FILLING_IOC=0, TRADE_RETCODE_DONE=10009,
    symbol_info_tick=lambda s: types.SimpleNamespace(bid=4374.6, ask=4374.8),
    order_send=lambda r: (sent.append(r), types.SimpleNamespace(retcode=10009, price=4374.6))[1])
acct = types.SimpleNamespace(login=1514166963)
BOTS = [GoldBreakout0630(), IndexBreakoutUSOpen()]

# 1. our position, session long over -> closed, with an opposing order
mt5.positions_get = lambda **k: [P(777,"XAUUSD")]
assert C.time_exits(mt5, acct, BOTS) == 1, "did not close an expired position"
assert sent[0]["position"] == 777 and sent[0]["type"] == mt5.ORDER_TYPE_SELL
assert sent[0]["volume"] == 0.03
print(f"  closed ticket 777 with {sent[0]['type']=} volume {sent[0]['volume']}")

# 2. someone else's magic -> never touched
sent.clear(); mt5.positions_get = lambda **k: [P(888,"XAUUSD",mg=880001)]
assert C.time_exits(mt5, acct, BOTS) == 0 and not sent, "touched a foreign position"

# 3. our magic but NO ledger row -> refuse, do not guess
mt5.positions_get = lambda **k: [P(999,"XAUUSD")]
assert C.time_exits(mt5, acct, BOTS) == 0 and not sent, "closed a position it could not identify"

# 4. symbol mismatch against the ledger -> refuse
mt5.positions_get = lambda **k: [P(777,"US100.cash")]
assert C.time_exits(mt5, acct, BOTS) == 0 and not sent, "closed on a symbol mismatch"

# 5. session still open -> left alone
C.TRADES.write_text("")
NOW = pd.Timestamp.now(tz="Europe/London")
C.append_trade({"intent_id":"a2","strategy_id":"BOT_A_gold_0630_breakout","symbol":"XAUUSD",
                "ticket":555,"timestamp":NOW.isoformat()})
mt5.positions_get = lambda **k: [P(555,"XAUUSD")]
n = C.time_exits(mt5, acct, BOTS)
if NOW.hour < 16:
    assert n == 0 and not sent, "closed a position whose session is still open"
    print("  live session left alone")
print("TIME EXIT CHECKS PASS")
