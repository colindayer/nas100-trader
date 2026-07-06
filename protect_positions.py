"""
protect_positions.py -- attach a protective stop-loss to any currently-open MT5
position that has none (sl == 0). One-time cleanup for positions opened BEFORE the
broker-side SL/TP fix. Default protective stop = 1.5% from current price.

Run on the VPS:  python protect_positions.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mt5_broker import MT5Broker

STOP = 0.015  # 1.5% protective stop (matches the sweep/S1 stop distance)

b = MT5Broker()
m = b._mt5
positions = m.positions_get() or []
if not positions:
    print("no open positions")
    sys.exit(0)

for p in positions:
    if p.sl and p.sl != 0.0:
        print(f"  {p.symbol} #{p.ticket}: already protected (SL={p.sl})")
        continue
    tick = m.symbol_info_tick(p.symbol)
    if p.type == m.POSITION_TYPE_BUY:
        sl = tick.bid * (1 - STOP)
    else:
        sl = tick.ask * (1 + STOP)
    req = {"action": m.TRADE_ACTION_SLTP, "position": p.ticket,
           "symbol": p.symbol, "sl": float(sl), "tp": float(getattr(p, "tp", 0.0) or 0.0)}
    res = m.order_send(req)
    ok = res is not None and res.retcode == m.TRADE_RETCODE_DONE
    if ok:
        print(f"  {p.symbol} #{p.ticket}: protected -> SL={sl:.2f} (was naked)")
    else:
        rc = getattr(res, "retcode", "?"); cm = getattr(res, "comment", m.last_error())
        print(f"  {p.symbol} #{p.ticket}: FAILED retcode={rc} {cm}")

print("done")
