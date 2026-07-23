"""dry_run_sizing.py -- watch DETERMINISTIC_RISK behave, offline, before risking anything.

Faithful to live_trader: risk$ per trade = equity * RISK_Sx * vix_mult * RISK_SCALE.
Deterministic mode: vix_mult in {0 pause, 1 trade}, RISK_SCALE=1 -> risk$ = equity*RISK_Sx.
No broker, no orders -- pure sizing preview. Real bot dry-run:
  DETERMINISTIC_RISK=1 python3 live_trader.py --broker mt5 --dry-run
"""
RISK = {"S1":0.0070,"S2":0.0050,"S3":0.0040,"S4":0.0040,"S5":0.0075,"BTC":0.0060}
STOP = {"S1":0.015,"S2":0.012,"S3":0.020,"S4":0.015,"S5":0.010,"BTC":0.025}
PRICE = {"S1":29800,"S2":2000,"S3":180,"S4":29800,"S5":180,"BTC":64000}

def vix_mult(vix, det): return 0.0 if vix>25 else (1.0 if det else (0.5 if vix>=20 else 1.0))
def size(strat, equity, vix, throttle, det):
    vm = vix_mult(vix, det); rs = 1.0 if det else throttle
    risk_frac = RISK[strat]*vm*rs
    risk_usd = equity*risk_frac
    lots = risk_usd/(PRICE[strat]*STOP[strat]) if risk_frac>0 else 0.0
    return risk_frac, risk_usd, lots

# a realistic sequence: same strategy across changing VIX/drawdown states
EQ = 50000
print(f"Account ${EQ:,} | 'watch' each setup: CURRENT (VIX-step x DD-throttle) vs DETERMINISTIC\n")
print(f"{'setup':16s} {'VIX':>4s} {'thr':>4s} | {'CUR risk%':>9s} {'CUR $':>7s} {'CUR lots':>8s} | {'DET risk%':>9s} {'DET $':>6s} {'DET lots':>8s}")
seq = [("S5 ORB",18,1.00),("S5 ORB",22,0.70),("S5 ORB",18,0.55),("S5 ORB",22,1.00),
       ("S1 sweep",18,0.80),("S1 sweep",27,0.50),("S2 gold",18,1.00),("BTC sweep",21,0.65)]
for label,vix,thr in seq:
    strat=label.split()[0]
    cf,cu,cl = size(strat,EQ,vix,thr,False)
    df,du,dl = size(strat,EQ,vix,thr,True)
    tag = "PAUSE" if df==0 else ""
    print(f"{label:16s} {vix:>4} {thr:>4.2f} | {cf:>8.3%} {cu:>7.0f} {cl:>8.3f} | {df:>8.3%} {du:>6.0f} {dl:>8.3f} {tag}")
print("\nCURRENT: risk swings trade-to-trade (VIX 0.5x step x DD throttle) -> erratic curve.")
print("DETERMINISTIC: fixed risk% per strategy every time; only pauses in extreme VIX (>25).")
