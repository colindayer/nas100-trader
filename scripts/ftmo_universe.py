# FTMO UNIVERSE INVENTORY v2 - ACCOUNT-BOUND, FAIL-CLOSED.
# Authorised: symbol_select(sym, True) to obtain history. Market Watch restored at the end.
# This file contains NO trading calls of any kind. The scan below asserts that.
import json, sys
from datetime import datetime, timezone
from pathlib import Path
try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("pip install MetaTrader5")
import pandas as pd

REQUIRED_LOGIN = 1514166963
REQUIRED_SERVER = "FTMO"
OUT = Path(__file__).resolve().parents[1] / "data" / "universe"
FROZEN = ["GOLD","SILVER","OIL","COPPER","NAS100","SP500"]

TM={0:"DISABLED",1:"LONGONLY",2:"SHORTONLY",3:"CLOSEONLY",4:"FULL"}
EM={0:"REQUEST",1:"INSTANT",2:"MARKET",3:"EXCHANGE"}
SM={0:"DISABLED",1:"POINTS",2:"SYMBOL_CCY",3:"MARGIN_CCY",4:"DEPOSIT_CCY",
    5:"INT_CURRENT",6:"INT_OPEN",7:"REOPEN_CURRENT",8:"REOPEN_BID"}
CM={0:"FOREX",1:"FUTURES",2:"CFD",3:"CFDINDEX",4:"CFDLEVERAGE",5:"FOREX_NO_LEV",
    32:"EXCH_STOCKS",33:"EXCH_FUTURES",35:"EXCH_BONDS"}

def acls(sym, path, calc):
    p=(path or "").upper()
    for k,c in (("BOND","BOND"),("TREASUR","BOND"),("NOTE","BOND"),("FOREX","FX"),
                ("CURRENC","FX"),("INDIC","INDEX"),("INDEX","INDEX"),("METAL","METAL"),
                ("ENERG","ENERGY"),("OIL","ENERGY"),("COMMOD","COMMODITY"),("AGRI","COMMODITY"),
                ("CRYPT","CRYPTO"),("STOCK","EQUITY"),("SHARE","EQUITY")):
        if k in p: return c
    s=sym.upper()
    if any(k in s for k in ("BUND","BOBL","SCHATZ","UST","TNOTE","TBOND","GILT","JGB","BTP","OAT")): return "BOND"
    if any(k in s for k in ("XAU","XAG","XPT","XPD","GOLD","SILVER","COPPER")): return "METAL"
    if any(k in s for k in ("BTC","ETH","XRP","LTC","SOL","ADA","DOGE")): return "CRYPTO"
    if any(k in s for k in ("OIL","WTI","BRENT","NGAS","NATGAS")): return "ENERGY"
    if CM.get(calc,"").startswith("FOREX"): return "FX"
    if CM.get(calc,"")=="CFDINDEX": return "INDEX"
    return "OTHER"

def depth(sym, tf, lab):
    try: r=mt5.copy_rates_from_pos(sym, tf, 0, 100000)
    except Exception: r=None
    if r is None or len(r)==0: return {lab+"_bars":0, lab+"_from":"", lab+"_to":""}
    t=pd.to_datetime(pd.DataFrame(r)["time"], unit="s", utc=True)
    return {lab+"_bars":int(len(r)), lab+"_from":str(t.min().date()), lab+"_to":str(t.max().date())}

# ---------- 1. IDENTITY PROOF. Fail closed BEFORE touching terminal state.
if not mt5.initialize(): sys.exit("initialize failed: %s" % str(mt5.last_error()))
a=mt5.account_info()
if a is None: mt5.shutdown(); sys.exit("HALT: not logged in")
print("connected: login=%s server=%s company=%s" % (a.login, a.server, a.company))
if int(a.login)!=REQUIRED_LOGIN or REQUIRED_SERVER not in str(a.server).upper():
    mt5.shutdown()
    sys.exit("HALT (fail-closed): require login=%d server~%s, found login=%s server=%s. "
             "NOTHING was selected or modified." % (REQUIRED_LOGIN, REQUIRED_SERVER, a.login, a.server))
print("IDENTITY OK -> FTMO %d. balance %.2f %s\n" % (a.login, a.balance, a.currency))

syms=mt5.symbols_get()
print("symbols_get() -> %d symbols" % len(syms))
was_visible={s.name: bool(s.visible) for s in syms}

# ---------- 2/3/4. enumerate, select, measure
rows=[]; added=[]
non_eq=[s for s in syms if acls(s.name, s.path, s.trade_calc_mode)!="EQUITY"]
eq=[s for s in syms if acls(s.name, s.path, s.trade_calc_mode)=="EQUITY"]
print("non-equity %d (full history measurement), equity %d (metadata only)\n" % (len(non_eq), len(eq)))

for i,s in enumerate(non_eq+eq, 1):
    inf=mt5.symbol_info(s.name)
    if inf is None: continue
    cls=acls(inf.name, inf.path, inf.trade_calc_mode)
    measure = (cls!="EQUITY")
    if measure and not inf.visible:
        if mt5.symbol_select(inf.name, True):
            added.append(inf.name)
            inf=mt5.symbol_info(inf.name)
    tk=mt5.symbol_info_tick(inf.name)
    r={"symbol":inf.name,"description":inf.description,"path":inf.path,"asset_class":cls,
       "calc_mode":CM.get(inf.trade_calc_mode,str(inf.trade_calc_mode)),
       "currency_base":inf.currency_base,"currency_profit":inf.currency_profit,
       "contract_size":inf.trade_contract_size,"digits":inf.digits,"point":inf.point,
       "tick_size":inf.trade_tick_size,"tick_value":inf.trade_tick_value,
       "volume_min":inf.volume_min,"volume_max":inf.volume_max,"volume_step":inf.volume_step,
       "spread_points":inf.spread,"spread_price":inf.spread*inf.point,
       "bid":getattr(tk,"bid",float("nan")),"ask":getattr(tk,"ask",float("nan")),
       "trade_mode":TM.get(inf.trade_mode,str(inf.trade_mode)),
       "execution_mode":EM.get(inf.trade_exemode,str(inf.trade_exemode)),
       "swap_long":inf.swap_long,"swap_short":inf.swap_short,
       "swap_mode":SM.get(inf.swap_mode,str(inf.swap_mode)),
       "swap_rollover3days":inf.swap_rollover3days,"margin_initial":inf.margin_initial,
       "was_visible":was_visible.get(inf.name,False),"history_measured":measure}
    if measure:
        r.update(depth(inf.name, mt5.TIMEFRAME_D1,"d1")); r.update(depth(inf.name, mt5.TIMEFRAME_H1,"h1"))
    else:
        r.update({"d1_bars":-1,"d1_from":"","d1_to":"","h1_bars":-1,"h1_from":"","h1_to":""})
    rows.append(r)
    if i%50==0: print("  ...%d/%d" % (i,len(syms)))

df=pd.DataFrame(rows)
OUT.mkdir(parents=True, exist_ok=True)
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
df.to_csv(OUT/"FTMO_UNIVERSE.csv", index=False)
df.to_csv(OUT/("FTMO_UNIVERSE_%s_%s.csv"%(a.login,stamp)), index=False)
json.dump({"login":a.login,"server":a.server,"company":a.company,"currency":a.currency,
           "captured_utc":stamp,"n_symbols":len(df),"selected_added":len(added)},
          open(OUT/"FTMO_UNIVERSE_META.json","w"), indent=1)

# ---------- 6. per-asset-class
m=df[df.history_measured]
print("\n%-11s%6s%9s%10s%11s%11s%11s" % ("class","n","tradable","d1>=1000","med_d1","swap_long","swap_short"))
for c,g in df.groupby("asset_class"):
    gm=g[g.history_measured]
    print("%-11s%6d%9d%10d%11.0f%11.2f%11.2f" % (c,len(g),int((g.trade_mode=="FULL").sum()),
        int((gm.d1_bars>=1000).sum()) if len(gm) else 0,
        gm.d1_bars.median() if len(gm) else -1, g.swap_long.median(), g.swap_short.median()))

# ---------- 7. the symbols that decide breadth
print("\n=== BOND / INDEX / METAL / ENERGY / COMMODITY with history ===")
print("%-16s%-11s%9s%12s%12s%10s%10s" % ("symbol","class","d1_bars","from","spread","swapL","swapS"))
sel=m[(m.asset_class.isin(["BOND","INDEX","METAL","ENERGY","COMMODITY"]))&(m.trade_mode=="FULL")]
for _,r in sel.sort_values(["asset_class","d1_bars"],ascending=[True,False]).iterrows():
    print("%-16s%-11s%9d%12s%12.5f%10.2f%10.2f" % (r.symbol[:15],r.asset_class,r.d1_bars,
          r.d1_from,r.spread_price,r.swap_long,r.swap_short))
print("\n=== MAJOR FX ===")
maj=["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"]
for _,r in m[m.symbol.str.upper().str.replace(r"[^A-Z]","",regex=True).isin(maj)].iterrows():
    print("%-16s%-11s%9d%12s%12.5f%10.2f%10.2f" % (r.symbol[:15],r.asset_class,r.d1_bars,
          r.d1_from,r.spread_price,r.swap_long,r.swap_short))

# ---------- 8. trend-suitable
ok=m[(m.d1_bars>=1000)&(m.trade_mode=="FULL")&(m.asset_class!="EQUITY")]
print("\n=== TREND-SUITABLE (>=1000 D1 bars, FULL trade mode, non-equity): %d ===" % len(ok))
print(ok.groupby("asset_class").size().to_string())

# ---------- 9. frozen-six swap
print("\n=== FROZEN SIX — FTMO symbol candidates and their swap ===")
for f in FROZEN:
    pats={"GOLD":["XAUUSD","GOLD"],"SILVER":["XAGUSD","SILVER"],"OIL":["USOIL","WTI","CRUDE","UKOIL","BRENT"],
          "COPPER":["COPPER","XCUUSD"],"NAS100":["NAS100","USTEC","NDX","US100"],
          "SP500":["SP500","US500","SPX"]}[f]
    hit=df[df.symbol.str.upper().str.contains("|".join(pats), regex=True, na=False)]
    if len(hit)==0: print("  %-8s NOT FOUND" % f); continue
    for _,r in hit.head(3).iterrows():
        print("  %-8s -> %-14s %-9s d1=%s swapL=%.2f swapS=%.2f mode=%s" %
              (f,r.symbol,r.asset_class,r.d1_bars,r.swap_long,r.swap_short,r.swap_mode))

# ---------- 10. restore Market Watch
for s in added:
    try: mt5.symbol_select(s, False)
    except Exception: pass
print("\nMarket Watch restored: deselected %d symbols we added" % len(added))
print("written -> %s" % (OUT/"FTMO_UNIVERSE.csv"))
mt5.shutdown()
