"""
Macro event filter: do the system's worst days/months cluster around scheduled
high-impact events (FOMC, NFP, CPI)? If so, skipping trades on event days should
cut the worst-month tail — letting us size up safely. Tested on combined 3-pillar P&L.
"""
import pandas as pd, numpy as np, io, contextlib, warnings
warnings.filterwarnings("ignore")
g={}
with contextlib.redirect_stdout(io.StringIO()):
    exec(open("combined_3pillar.py").read(), g)
pnl = g["combined"].sort_index(); pnl.index = pd.to_datetime(pnl.index)
base = 10_000.0

# ── high-impact event days ────────────────────────────────────────────────────
FOMC = pd.to_datetime([  # announcement days 2019-2026 (best-effort)
 "2019-01-30","2019-03-20","2019-05-01","2019-06-19","2019-07-31","2019-09-18","2019-10-30","2019-12-11",
 "2020-01-29","2020-03-03","2020-03-15","2020-04-29","2020-06-10","2020-07-29","2020-09-16","2020-11-05","2020-12-16",
 "2021-01-27","2021-03-17","2021-04-28","2021-06-16","2021-07-28","2021-09-22","2021-11-03","2021-12-15",
 "2022-01-26","2022-03-16","2022-05-04","2022-06-15","2022-07-27","2022-09-21","2022-11-02","2022-12-14",
 "2023-02-01","2023-03-22","2023-05-03","2023-06-14","2023-07-26","2023-09-20","2023-11-01","2023-12-13",
 "2024-01-31","2024-03-20","2024-05-01","2024-06-12","2024-07-31","2024-09-18","2024-11-07","2024-12-18",
 "2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17","2025-10-29","2025-12-10",
 "2026-01-28","2026-03-18"])
# NFP = first Friday each month; CPI ~13th (approx)
alld = pd.date_range(pnl.index.min(), pnl.index.max(), freq="D")
nfp = pd.to_datetime([d for m,grp in pd.Series(alld).groupby([alld.year,alld.month])
                      for d in [grp[grp.dt.weekday==4].min()] if pd.notna(d)])
cpi = pd.to_datetime([f"{y}-{m:02d}-13" for y in range(2019,2027) for m in range(1,13)], errors="coerce")
events = pd.DatetimeIndex(FOMC).union(nfp).union(cpi)
# event window = event day +/- 0 (the day itself)
is_event = pnl.index.normalize().isin(events.normalize())

# ── analysis ──────────────────────────────────────────────────────────────────
ev = pnl[is_event]; nev = pnl[~is_event]
print("="*64); print("MACRO EVENT FILTER — do losses cluster on event days?"); print("="*64)
print(f"  Event days: {is_event.sum()} | non-event: {(~is_event).sum()}")
print(f"  Mean P&L  event: ${ev.mean():+.1f} | non-event: ${nev.mean():+.1f}")
print(f"  Std  P&L  event: ${ev.std():.1f} | non-event: ${nev.std():.1f}")
worst = pnl.nsmallest(20)
print(f"  Of the 20 WORST days, {worst.index.normalize().isin(events.normalize()).sum()}/20 are event days "
      f"(expected if random: ~{20*is_event.mean():.0f})")

def metrics(series, label):
    idx=pd.date_range(series.index.min(),series.index.max(),freq="D")
    p=series.reindex(idx).fillna(0); eq=base+p.cumsum()
    mdd=((eq-eq.cummax())/eq.cummax()).min()
    monthly=eq.resample("ME").last().pct_change(); wm=monthly.min()
    tot=(eq.iloc[-1]/base-1)
    print(f"  {label:<26} total {tot:>+7.1%} | MaxDD {mdd:>+6.1%} | worstMonth {wm:>+6.1%}")
    return tot,mdd,wm

print("\n[Filter test] skip ALL trades on event days:")
filtered = pnl.copy(); filtered[is_event] = 0.0
metrics(pnl, "baseline (trade all)")
metrics(filtered, "skip event days")
print("="*64)
print("If skip-event has shallower worstMonth/MaxDD with similar total = filter helps.")
