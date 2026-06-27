"""
Performance report for the full 6-strategy system (NET of transaction costs).
Builds ONE continuous daily equity curve for the combined portfolio (6 equal
$10k sleeves) over 2019-2023, then generates pro KPIs + a QuantStats HTML
tearsheet (the "Risk Management & KPIs" / "Automatic P&L Reporting" layer).

Run:  python3 perf_report.py   ->  prints KPIs, writes perf_tearsheet.html
"""
import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")

# Reuse all signal-building + helpers from full_yearly (everything before "# ── run all")
_src = open("full_yearly.py").read().split("# ── run all")[0]
exec(_src)

# ── continuous trade-collecting engines (no yearly reset; record exit-date P&L) ──
def trades_intraday(sig_col, risk, sl, rr, short=False):
    cap=10_000; rows=[]; in_t=False; entry=stop=tgt=sh=0.; ds=cap; cur=None; lock=False; day_traded=None
    for i in range(1,len(q)):
        d=q.index[i].date(); price=float(q["Close"].iloc[i]); s=int(q[sig_col].iloc[i-1]); vm=vmult(q.index[i-1].date())
        if d!=cur: cur=d; ds=cap; lock=False
        if (cap-ds)/max(ds,1)<=-0.05 or (cap-10_000)/10_000<=-0.10: lock=True
        if lock: continue
        if in_t:
            pnl=None
            if not short:
                if price<=stop: pnl=sh*(stop-entry)-sh*(entry+stop)*SLIP
                elif price>=tgt: pnl=sh*(tgt-entry)-sh*(entry+tgt)*SLIP
            else:
                if price>=stop: pnl=sh*(entry-price)-sh*(entry+stop)*SLIP
                elif price<=tgt: pnl=sh*(entry-price)-sh*(entry+tgt)*SLIP
            if pnl is not None: cap+=pnl; rows.append((d,pnl)); in_t=False
        elif s==1 and vm>0 and day_traded!=d:
            in_t=True; day_traded=d; entry=price
            if not short: stop=price*(1-sl); tgt=price*(1+sl*rr)
            else: stop=price*(1+sl); tgt=price*(1-sl*rr)
            sh=(cap*risk*vm)/(price*sl)
    return rows

def trades_daily(df, sig, risk, sl, rr, hold=None):
    cap=10_000; rows=[]; in_t=False; entry=stop=tgt=sh=0.; held=0
    for i in range(1,len(df)):
        d=df.index[i].date(); price=float(df["Close"].iloc[i]); s=int(df[sig].iloc[i-1])
        if in_t:
            held+=1; pnl=None
            if hold is None:
                if price<=stop: pnl=sh*(stop-entry)-sh*(entry+stop)*SLIP
                elif price>=tgt: pnl=sh*(tgt-entry)-sh*(entry+tgt)*SLIP
            else:
                if price<=stop or price>=tgt or held>=hold: pnl=sh*(price-entry)-sh*(entry+price)*SLIP
            if pnl is not None: cap+=pnl; rows.append((d,pnl)); in_t=False
        elif s==1:
            in_t=True; entry=price; stop=price*(1-sl); tgt=price*(1+sl*rr); held=0; sh=(cap*risk)/(price*sl)
    return rows

print("Running 6 strategies (continuous, net of costs)...")
all_trades = (
    trades_intraday("S1",0.007,0.015,3.0) +
    trades_intraday("S4",0.005,0.015,3.0) +
    trades_intraday("S5L",0.005,0.010,2.5) +
    trades_intraday("S5S",0.003,0.010,2.5,short=True) +
    trades_daily(gld,"FVG",0.005,0.012,2.0) +
    trades_daily(qd,"S3",0.004,0.020,2.5,hold=5)
)

# ── build combined daily equity curve ────────────────────────────────────────
pnl_by_day = pd.Series(0.0, index=pd.bdate_range(START,END))
for d,pnl in all_trades:
    ts=pd.Timestamp(d)
    if ts in pnl_by_day.index: pnl_by_day[ts]+=pnl
    else: pnl_by_day = pd.concat([pnl_by_day, pd.Series([pnl],index=[ts])])
pnl_by_day=pnl_by_day.sort_index()
# Single shared account: all 6 strategies run on ONE $10k base. Valid because each
# risks <1%/trade (max simultaneous risk ~3%), so they coexist and P&L ~adds.
# This is the realistic deployment model (one prop account, many strategies).
START_CAP=10_000.0
equity=START_CAP+pnl_by_day.cumsum()
returns=equity.pct_change().fillna(0.0)
returns.index=pd.to_datetime(returns.index)

# ── KPIs (manual, so it works even without quantstats) ───────────────────────
tr=pd.Series([p for _,p in all_trades])
days=(returns.index[-1]-returns.index[0]).days
cagr=(equity.iloc[-1]/START_CAP)**(365.25/days)-1
ann_vol=returns.std()*np.sqrt(252)
sharpe=(returns.mean()*252)/(returns.std()*np.sqrt(252)) if returns.std()>0 else 0
downside=returns[returns<0].std()*np.sqrt(252)
sortino=(returns.mean()*252)/downside if downside>0 else 0
dd=((equity-equity.cummax())/equity.cummax()); maxdd=dd.min()
pf=tr[tr>0].sum()/abs(tr[tr<0].sum()) if (tr<0).any() else 99.9
print("\n"+"="*56)
print("COMBINED 6-STRATEGY KPIs  (net of costs, single $10k account)")
print("="*56)
print(f"  Total trades:      {len(tr)}  ({len(tr)/5:.0f}/yr)")
print(f"  Total return:      {(equity.iloc[-1]/START_CAP-1):+.1%}")
print(f"  CAGR:              {cagr:+.1%}")
print(f"  Ann. volatility:   {ann_vol:.1%}")
print(f"  Sharpe ratio:      {sharpe:.2f}")
print(f"  Sortino ratio:     {sortino:.2f}")
print(f"  Max drawdown:      {maxdd:.1%}")
print(f"  Win rate:          {(tr>0).mean():.0%}")
print(f"  Profit factor:     {pf:.2f}")
print(f"  Best day:          {returns.max():+.2%}")
print(f"  Worst day:         {returns.min():+.2%}")
print("="*56)

# ── QuantStats HTML tearsheet ─────────────────────────────────────────────────
try:
    import quantstats as qs
    qs.reports.html(returns, output="perf_tearsheet.html",
                    title="6-Strategy System (net of costs)", download_filename="perf_tearsheet.html")
    print("\n✓ Tearsheet written: perf_tearsheet.html (open in a browser)")
except Exception as e:
    print(f"\n(QuantStats tearsheet skipped: {e})")

# ── Live trade log: parse logs/trader.log + emit daily summary ────────────────
import os, re
from datetime import date as _date

_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "logs", "trader.log")
_summary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "logs", "daily_summary.log")

def parse_live_log():
    """Parse FILL lines from trader.log → {date: (n_fills, pnl_list)}."""
    if not os.path.exists(_log_path):
        return {}
    # Log line format (from alerts.py): "2026-06-27 19:11:00,123 INFO FILL S1 BUY 12.0 QQQ"
    # We capture fills by date; actual P&L requires matching entry vs exit prices,
    # so here we count fills and flag active sessions.
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}.*INFO FILL (\w+) (\w+) ([\d.]+) (\w+)")
    by_date: dict = {}
    with open(_log_path) as f:
        for line in f:
            m = pattern.search(line)
            if m:
                dt, tag, side, qty, sym = m.groups()
                by_date.setdefault(dt, []).append(
                    dict(tag=tag, side=side, qty=float(qty), sym=sym))
    return by_date

def emit_daily_summary():
    fills_by_date = parse_live_log()
    if not fills_by_date:
        print("\n(No live fill records found in logs/trader.log)")
        return
    os.makedirs(os.path.dirname(_summary_path), exist_ok=True)
    lines = []
    for dt in sorted(fills_by_date.keys()):
        fills = fills_by_date[dt]
        n = len(fills)
        detail = ", ".join(f"{f['tag']} {f['side']} {f['qty']:.0f} {f['sym']}"
                           for f in fills)
        summary = f"{dt} | fills: {n} | {detail}"
        lines.append(summary)
    with open(_summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n── Live Trade Log Summary ({len(lines)} session-days) ──")
    for l in lines[-10:]:  # show last 10
        print(f"  {l}")
    print(f"Full summary: {_summary_path}")

emit_daily_summary()
