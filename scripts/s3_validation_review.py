"""
S3 Validation Review: Research vs Live Implementation
=====================================================
Reconstructs both versions exactly, runs on identical data, compares all metrics.

RESEARCH S3 (full_yearly.py validated lineage):
  - Universe: QQQ only
  - Volume signal: Volume > 1.3 * ma20 (simple ratio, 20-day MA)
  - Price signal: Close > Open (green candle)
  - Regime filters: SPY EMA50 > EMA200 (bull) + GEX < 0
  - Risk: 0.4% per trade
  - Stop: 2.0%
  - Target: 2.5 * stop (RR = 2.5)  -> 5% target
  - Hold: max 5 days
  - Exit: stop hit OR target hit OR time exit

LIVE S3 (live_trader.py current):
  - Universe: ["QQQ", "GLD", "GDX", "SLV", "USO"] (but we test QQQ-only for apples-to-apples)
  - Volume signal: z-score > 1.5  where z = (V - mean66) / std66
  - Price signal: (Close - Open) / Open > 0.01  (1% daily return)
  - Regime filter: VIX mult > 0 (VIX < 25)
  - Risk: 0.4% per trade
  - Stop: 2.0%
  - Target: NONE (no RR target)
  - Hold: max 5 days
  - Exit: stop hit OR time exit

Runs on identical QQQ daily data (aggregated from hourly CSV).
Periods: 2019-2023 (in-sample, GEX available) and 2024-2026 (OOS).
"""
import pandas as pd
import numpy as np
import pytz
import warnings
import yfinance as yf
from datetime import date, timedelta
warnings.filterwarnings("ignore")

SLIP = 0.0003  # 3 bps per side

# ── DATA ──────────────────────────────────────────────────────────────────────
print("Loading data...")

# QQQ hourly → aggregate to daily
df = pd.read_csv("qqq_hourly_7y.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df[df["symbol"] == "QQQ"].copy()
eastern = pytz.timezone("US/Eastern")
df["et"] = df["timestamp"].dt.tz_convert(eastern)
df["Date"] = df["et"].dt.date

# Aggregate to daily
qd = df.groupby("Date").agg({
    "open": "first", "high": "max", "low": "min",
    "close": "last", "volume": "sum"
}).rename(columns={"open": "Open", "high": "High", "low": "Low",
                    "close": "Close", "volume": "Volume"})
qd.index = pd.to_datetime(qd.index)
print(f"QQQ daily: {qd.index.min().date()} → {qd.index.max().date()}, {len(qd)} bars")

# GEX
gex = pd.read_csv("gex_history.csv", index_col=0)
gex.index = pd.to_datetime(gex.index).date
gex_map = gex["gex"].to_dict() if "gex" in gex.columns else gex.iloc[:, 0].to_dict()

# SPY for regime
spy_raw = yf.download("SPY", start="2018-01-01", end=str(date.today()),
                       progress=False, auto_adjust=True)
if isinstance(spy_raw.columns, pd.MultiIndex):
    spy_raw.columns = spy_raw.columns.get_level_values(0)
spy_close = spy_raw["Close"].squeeze()
spy_close.index = pd.to_datetime(spy_close.index).tz_localize(None).normalize()
spy_ema50 = spy_close.ewm(span=50).mean()
spy_ema200 = spy_close.ewm(span=200).mean()
spy_bull = (spy_ema50 > spy_ema200)

# VIX
vix_raw = yf.download("^VIX", start="2018-01-01", end=str(date.today()),
                       progress=False)
if isinstance(vix_raw.columns, pd.MultiIndex):
    vix_raw.columns = vix_raw.columns.get_level_values(0)
vix = vix_raw["Close"].squeeze()
vix.index = pd.to_datetime(vix.index).tz_localize(None).normalize()
vix_ma21 = vix.rolling(21).mean()

def asof_map(series, dates):
    """Forward-fill series onto given dates."""
    s = series.reindex(series.index.union(pd.DatetimeIndex(dates))).ffill()
    result = s.asof(pd.DatetimeIndex(dates))
    return pd.Series(result.values, index=[t.date() if hasattr(t, 'date') else t for t in pd.DatetimeIndex(dates)])

all_dates = qd.index.date
bull_map = asof_map(spy_bull, all_dates)
vix_map = asof_map(vix_ma21, all_dates)
vix_level_map = asof_map(vix, all_dates)

# ── FEATURE ENGINEERING ───────────────────────────────────────────────────────
qd["ma20"] = qd["Volume"].rolling(20).mean()
qd["mean66"] = qd["Volume"].rolling(66).mean().shift(1)
qd["std66"] = qd["Volume"].rolling(66).std().shift(1)
qd["z_score"] = (qd["Volume"] - qd["mean66"]) / qd["std66"]
qd["vol_ratio"] = qd["Volume"] / qd["ma20"]
qd["dayret"] = (qd["Close"] - qd["Open"]) / qd["Open"]
qd["green"] = qd["Close"] > qd["Open"]
qd["bull"] = [bool(bull_map.get(d, True)) for d in qd.index.date]
qd["gex_neg"] = [gex_map.get(d, 0) < 0 if d in gex_map else True for d in qd.index.date]
qd["vix_level"] = [vix_level_map.get(d, 20.0) for d in qd.index.date]

def vix_mult(vix_val):
    if pd.isna(vix_val): return 1.0
    if vix_val > 25: return 0.0
    if vix_val >= 20: return 0.5
    return 1.0

qd["vix_mult"] = qd["vix_level"].apply(vix_mult)

# ── SIGNAL GENERATION ────────────────────────────────────────────────────────
# Research S3 signal
qd["S3_research"] = (
    (qd["vol_ratio"] > 1.3) &
    qd["green"] &
    qd["bull"] &
    qd["gex_neg"]
).astype(int)

# Live S3 signal (single-symbol QQQ version)
qd["S3_live"] = (
    (qd["z_score"] > 1.5) &
    (qd["dayret"] > 0.01) &
    (qd["vix_mult"] > 0)
).astype(int)

# Hybrid: research logic but with z-score > 1.5 instead of ratio > 1.3
qd["S3_z13_research_extras"] = (
    (qd["z_score"] > 1.5) &
    qd["green"] &
    qd["bull"] &
    qd["gex_neg"]
).astype(int)

# Hybrid: research logic with ratio > 1.3 but live extras (dayret > 0.01, vix gate)
qd["S3_ratio_live_extras"] = (
    (qd["vol_ratio"] > 1.3) &
    (qd["dayret"] > 0.01) &
    (qd["vix_mult"] > 0)
).astype(int)


# ── BACKTEST ENGINE ──────────────────────────────────────────────────────────
def backtest_s3(qd_input, signal_col, start_date, end_date,
                risk=0.004, sl=0.02, rr=2.5, hold=5, use_target=True,
                slip=SLIP, init_cap=10_000):
    """
    Run S3 backtest on given data slice.
    Returns dict with trades list and equity curve.
    """
    mask = (qd_input.index >= pd.Timestamp(start_date)) & (qd_input.index <= pd.Timestamp(end_date))
    g = qd_input[mask].copy()

    cap = init_cap
    in_t = False
    entry = stop = tgt = sh = 0.0
    held = 0
    trades = []
    equity_curve = []

    for i in range(1, len(g)):
        d = g.index[i]
        price = float(g["Close"].iloc[i])
        s = int(g[signal_col].iloc[i - 1])  # signal from PREVIOUS day

        if in_t:
            held += 1
            if not (use_target and rr):  # live-style: no target
                if price <= stop or held >= hold:
                    exit_p = min(price, stop) if price <= stop else price
                    pnl = sh * (exit_p - entry) - sh * (entry + exit_p) * slip
                    cap += pnl
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": d,
                        "entry": entry,
                        "exit": exit_p,
                        "shares": sh,
                        "pnl": pnl,
                        "ret_pct": (exit_p - entry) / entry,
                        "bars_held": held,
                        "reason": "stop" if price <= stop else "time"
                    })
                    in_t = False
            else:  # research-style: has target
                if price <= stop:
                    pnl = sh * (stop - entry) - sh * (entry + stop) * slip
                    cap += pnl
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": d,
                        "entry": entry,
                        "exit": stop,
                        "shares": sh,
                        "pnl": pnl,
                        "ret_pct": (stop - entry) / entry,
                        "bars_held": held,
                        "reason": "stop"
                    })
                    in_t = False
                elif price >= tgt:
                    pnl = sh * (tgt - entry) - sh * (entry + tgt) * slip
                    cap += pnl
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": d,
                        "entry": entry,
                        "exit": tgt,
                        "shares": sh,
                        "pnl": pnl,
                        "ret_pct": (tgt - entry) / entry,
                        "bars_held": held,
                        "reason": "target"
                    })
                    in_t = False
                elif held >= hold:
                    pnl = sh * (price - entry) - sh * (entry + price) * slip
                    cap += pnl
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": d,
                        "entry": entry,
                        "exit": price,
                        "shares": sh,
                        "pnl": pnl,
                        "ret_pct": (price - entry) / entry,
                        "bars_held": held,
                        "reason": "time"
                    })
                    in_t = False
        elif s == 1:
            in_t = True
            entry_date = g.index[i]
            entry = price
            stop = price * (1 - sl)
            if use_target and rr:
                tgt = price * (1 + sl * rr)
            else:
                tgt = float('inf')
            held = 0
            sh = (cap * risk) / (price * sl)

        equity_curve.append({"date": d, "equity": cap})

    return {
        "trades": trades,
        "equity_curve": pd.DataFrame(equity_curve).set_index("date") if equity_curve else pd.DataFrame(),
        "final_cap": cap,
        "total_ret": (cap - init_cap) / init_cap,
    }


def compute_metrics(result, period_years, init_cap=10_000):
    """Compute all comparison metrics from a backtest result."""
    trades = result["trades"]
    if not trades:
        return {
            "trades_total": 0, "trades_per_year": 0, "CAGR": 0, "Sharpe": 0,
            "PF": 0, "MaxDD": 0, "expectancy": 0, "win_rate": 0, "avg_R": 0,
        }

    pnls = pd.Series([t["pnl"] for t in trades])
    rets = pd.Series([t["ret_pct"] for t in trades])

    # Win/loss
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    win_rate = len(wins) / len(trades) if trades else 0

    # Profit Factor
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')

    # Expectancy (per trade, in $)
    expectancy = pnls.mean()

    # Average R (return per trade / risk per trade)
    risk_per_trade = init_cap * 0.004  # 0.4% risk
    avg_R = rets.mean() / 0.02  # normalized by stop %

    # CAGR
    total_ret = result["total_ret"]
    CAGR = (1 + total_ret) ** (1 / period_years) - 1 if period_years > 0 else 0

    # Sharpe (annualized from trade returns)
    if rets.std() > 0:
        # Approximate annualization: trades_per_year periods per year
        trades_per_year = len(trades) / period_years
        Sharpe = (rets.mean() / rets.std()) * np.sqrt(trades_per_year) if trades_per_year > 0 else 0
    else:
        Sharpe = 0

    # MaxDD from equity curve
    eq = result["equity_curve"]
    if len(eq) > 0:
        eq["peak"] = eq["equity"].cummax()
        eq["dd"] = (eq["equity"] - eq["peak"]) / eq["peak"]
        MaxDD = eq["dd"].min()
    else:
        MaxDD = 0

    return {
        "trades_total": len(trades),
        "trades_per_year": len(trades) / period_years,
        "CAGR": CAGR,
        "Sharpe": Sharpe,
        "PF": pf,
        "MaxDD": MaxDD,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "avg_R": avg_R,
    }


def yearly_breakdown(result):
    """Return per-year return dict."""
    trades = result["trades"]
    yearly = {}
    for t in trades:
        y = t["exit_date"].year if hasattr(t["exit_date"], 'year') else pd.Timestamp(t["exit_date"]).year
        if y not in yearly:
            yearly[y] = 0.0
        yearly[y] += t["pnl"]
    # Convert to % return on $10k
    return {y: v / 10_000 for y, v in sorted(yearly.items())}


def oos_splits(result, n_splits=6):
    """Split the trade period into N equal segments and compute Sharpe for each."""
    trades = result["trades"]
    if len(trades) < n_splits:
        return [{"split": i+1, "trades": 0, "ret": 0, "Sharpe": 0} for i in range(n_splits)]

    dates = [t["exit_date"] for t in trades]
    min_d, max_d = min(dates), max(dates)
    total_days = (max_d - min_d).days if hasattr(max_d, 'days') else (pd.Timestamp(max_d) - pd.Timestamp(min_d)).days
    split_days = total_days / n_splits

    splits = []
    for i in range(n_splits):
        start = min_d + timedelta(days=i * split_days)
        end = min_d + timedelta(days=(i + 1) * split_days)

        seg_trades = [t for t in trades if start <= t["exit_date"] <= end]
        seg_pnls = [t["pnl"] for t in seg_trades]
        seg_rets = [t["ret_pct"] for t in seg_trades]

        if len(seg_trades) > 0 and np.std(seg_rets) > 0:
            sr = np.mean(seg_rets) / np.std(seg_rets) * np.sqrt(len(seg_trades))
        else:
            sr = 0

        splits.append({
            "split": i + 1,
            "start": str(start.date()) if hasattr(start, 'date') else str(start),
            "end": str(end.date()) if hasattr(end, 'date') else str(end),
            "trades": len(seg_trades),
            "ret": sum(seg_pnls) / 10_000,
            "Sharpe": sr,
        })
    return splits


# ── RUN ALL VARIANTS ──────────────────────────────────────────────────────────
# Period 1: 2019-2023 (in-sample, GEX available)
# Period 2: 2024-2026 (out-of-sample, no GEX - use True as fallback)
# Period 3: Full 2019-2026

variants = {
    "RESEARCH (ratio>1.3, green, bull, GEX<0, RR=2.5)": {
        "signal_col": "S3_research",
        "use_target": True,
        "rr": 2.5,
    },
    "LIVE (z>1.5, dayret>1%, VIX gate, no target)": {
        "signal_col": "S3_live",
        "use_target": False,
        "rr": None,
    },
    "HYBRID A: z>1.5 + research extras (bull, GEX, RR=2.5)": {
        "signal_col": "S3_z13_research_extras",
        "use_target": True,
        "rr": 2.5,
    },
    "HYBRID B: ratio>1.3 + live extras (dayret>1%, VIX, no target)": {
        "signal_col": "S3_ratio_live_extras",
        "use_target": False,
        "rr": None,
    },
}

periods = [
    ("2019-01-01", "2023-12-31", "IS 2019-2023", 5.0),
    ("2024-01-01", "2026-05-29", "OOS 2024-2026", 2.4),
    ("2019-01-01", "2026-05-29", "Full 2019-2026", 7.4),
]

all_results = {}

for vname, vcfg in variants.items():
    print(f"\n{'='*78}")
    print(f"  VARIANT: {vname}")
    print(f"{'='*78}")

    for start_d, end_d, plabel, pyrs in periods:
        result = backtest_s3(
            qd, vcfg["signal_col"],
            start_d, end_d,
            risk=0.004, sl=0.02,
            rr=vcfg["rr"], hold=5,
            use_target=vcfg["use_target"],
        )
        metrics = compute_metrics(result, pyrs)
        yearly = yearly_breakdown(result)
        splits = oos_splits(result, 6)

        key = f"{vname} | {plabel}"
        all_results[key] = {
            "metrics": metrics,
            "yearly": yearly,
            "splits": splits,
            "result": result,
        }

        m = metrics
        print(f"\n  [{plabel}]")
        print(f"    Trades: {m['trades_total']} ({m['trades_per_year']:.1f}/yr)")
        print(f"    CAGR:   {m['CAGR']:+.2%}")
        print(f"    Sharpe: {m['Sharpe']:.2f}")
        print(f"    PF:     {m['PF']:.2f}")
        print(f"    MaxDD:  {m['MaxDD']:+.2%}")
        print(f"    Expectancy: ${m['expectancy']:+.2f}/trade")
        print(f"    Win Rate:   {m['win_rate']:.1%}")
        print(f"    Avg R:      {m['avg_R']:+.3f}R")

        if yearly:
            yr_str = "  ".join(f"{y}: {r:+.1%}" for y, r in yearly.items())
            print(f"    Yearly: {yr_str}")

        print(f"    6-split OOS:")
        for sp in splits:
            print(f"      Split {sp['split']}: {sp['trades']} trades, ret={sp['ret']:+.2%}, Sharpe={sp['Sharpe']:.2f}")

# ── HEAD-TO-HEAD SUMMARY ──────────────────────────────────────────────────────
print(f"\n\n{'='*78}")
print("  HEAD-TO-HEAD: RESEARCH vs LIVE (on QQQ daily, identical data)")
print(f"{'='*78}")

for plabel in ["IS 2019-2023", "OOS 2024-2026", "Full 2019-2026"]:
    research_key = f"{list(variants.keys())[0]} | {plabel}"
    live_key = f"{list(variants.keys())[1]} | {plabel}"

    if research_key not in all_results or live_key not in all_results:
        continue

    rm = all_results[research_key]["metrics"]
    lm = all_results[live_key]["metrics"]

    print(f"\n  [{plabel}]")
    print(f"  {'Metric':<18} {'Research':>12} {'Live':>12} {'Delta':>12}")
    print(f"  {'-'*54}")

    for metric_name, fmt in [
        ("trades_total", "d"), ("trades_per_year", ".1f"),
        ("CAGR", ".2%"), ("Sharpe", ".2f"), ("PF", ".2f"),
        ("MaxDD", ".2%"), ("expectancy", ".2f"),
        ("win_rate", ".1%"), ("avg_R", ".3f"),
    ]:
        rv = rm[metric_name]
        lv = lm[metric_name]
        delta = lv - rv
        if fmt == "d":
            print(f"  {metric_name:<18} {rv:>12d} {lv:>12d} {delta:>+12d}")
        elif fmt == ".2%":
            print(f"  {metric_name:<18} {rv:>+12{fmt}} {lv:>+12{fmt}} {delta:>+12{fmt}}")
        else:
            print(f"  {metric_name:<18} {rv:>12{fmt}} {lv:>12{fmt}} {delta:>+12{fmt}}")

# ── ISOLATE THE Z>1.5 TIGHTENING EFFECT ──────────────────────────────────────
print(f"\n\n{'='*78}")
print("  ISOLATION: z>1.5 vs ratio>1.3 (same exit logic, same filters)")
print(f"{'='*78}")
print("  Testing whether z-score > 1.5 adds value over simple ratio > 1.3")
print("  Both use research filters (bull, GEX, RR=2.5) to isolate the volume measure")

for plabel in ["IS 2019-2023", "OOS 2024-2026", "Full 2019-2026"]:
    # Research = ratio>1.3 + research filters
    # Hybrid A = z>1.5 + research filters
    r_key = f"{list(variants.keys())[0]} | {plabel}"
    z_key = f"{list(variants.keys())[2]} | {plabel}"

    if r_key not in all_results or z_key not in all_results:
        continue

    rm = all_results[r_key]["metrics"]
    zm = all_results[z_key]["metrics"]

    print(f"\n  [{plabel}]")
    print(f"  {'Metric':<18} {'ratio>1.3':>12} {'z>1.5':>12} {'Delta':>12}")
    print(f"  {'-'*54}")

    for metric_name, fmt in [
        ("trades_total", "d"), ("trades_per_year", ".1f"),
        ("CAGR", ".2%"), ("Sharpe", ".2f"), ("PF", ".2f"),
        ("MaxDD", ".2%"), ("expectancy", ".2f"),
        ("win_rate", ".1%"), ("avg_R", ".3f"),
    ]:
        rv = rm[metric_name]
        zv = zm[metric_name]
        delta = zv - rv
        if fmt == "d":
            print(f"  {metric_name:<18} {rv:>12d} {zv:>12d} {delta:>+12d}")
        elif fmt == ".2%":
            print(f"  {metric_name:<18} {rv:>+12{fmt}} {zv:>+12{fmt}} {delta:>+12{fmt}}")
        else:
            print(f"  {metric_name:<18} {rv:>12{fmt}} {zv:>12{fmt}} {delta:>+12{fmt}}")

# ── ISOLATE THE EXIT LOGIC (RR target vs no target) ───────────────────────────
print(f"\n\n{'='*78}")
print("  ISOLATION: RR=2.5 target vs no target (same signal, same filters)")
print(f"{'='*78}")
print("  Testing whether the profit target adds or removes value")

for plabel in ["IS 2019-2023", "OOS 2024-2026", "Full 2019-2026"]:
    # Same signal (research signal), compare with/without target
    result_with = backtest_s3(qd, "S3_research", "2019-01-01" if "2019" in plabel else "2024-01-01",
                               "2023-12-31" if "2019" in plabel else "2026-05-29",
                               risk=0.004, sl=0.02, rr=2.5, hold=5, use_target=True)
    result_without = backtest_s3(qd, "S3_research", "2019-01-01" if "2019" in plabel else "2024-01-01",
                                  "2023-12-31" if "2019" in plabel else "2026-05-29",
                                  risk=0.004, sl=0.02, rr=None, hold=5, use_target=False)

    pyrs = 5.0 if "2019" in plabel else 2.4
    mw = compute_metrics(result_with, pyrs)
    mo = compute_metrics(result_without, pyrs)

    print(f"\n  [{plabel}] (research signal)")
    print(f"  {'Metric':<18} {'RR=2.5':>12} {'No target':>12} {'Delta':>12}")
    print(f"  {'-'*54}")

    for metric_name, fmt in [
        ("trades_total", "d"), ("trades_per_year", ".1f"),
        ("CAGR", ".2%"), ("Sharpe", ".2f"), ("PF", ".2f"),
        ("MaxDD", ".2%"), ("expectancy", ".2f"),
        ("win_rate", ".1%"), ("avg_R", ".3f"),
    ]:
        wv = mw[metric_name]
        ov = mo[metric_name]
        delta = ov - wv
        if fmt == "d":
            print(f"  {metric_name:<18} {wv:>12d} {ov:>12d} {delta:>+12d}")
        elif fmt == ".2%":
            print(f"  {metric_name:<18} {wv:>+12{fmt}} {ov:>+12{fmt}} {delta:>+12{fmt}}")
        else:
            print(f"  {metric_name:<18} {wv:>12{fmt}} {ov:>12{fmt}} {delta:>+12{fmt}}")


# ── SIGNAL OVERLAP ANALYSIS ──────────────────────────────────────────────────
print(f"\n\n{'='*78}")
print("  SIGNAL OVERLAP ANALYSIS (2019-2026)")
print(f"{'='*78}")

full_mask = qd.index >= pd.Timestamp("2019-01-01")
r_sig = qd.loc[full_mask, "S3_research"]
l_sig = qd.loc[full_mask, "S3_live"]
z_sig = qd.loc[full_mask, "S3_z13_research_extras"]

overlap = (r_sig == 1) & (l_sig == 1)
r_only = (r_sig == 1) & (l_sig == 0)
l_only = (r_sig == 0) & (l_sig == 1)
neither = (r_sig == 0) & (l_sig == 0)

print(f"  Research signals:    {int(r_sig.sum())}")
print(f"  Live signals:        {int(l_sig.sum())}")
print(f"  Overlap (both fire): {int(overlap.sum())}")
print(f"  Research-only:       {int(r_only.sum())}")
print(f"  Live-only:           {int(l_only.sum())}")
print(f"  Neither:             {int(neither.sum())}")
print()

# What % of research signals does the live filter remove?
if int(r_sig.sum()) > 0:
    pct_removed = int(r_only.sum()) / int(r_sig.sum())
    print(f"  Live filter REMOVES {pct_removed:.1%} of research signals")
    print(f"  (These are potentially profitable trades being filtered out)")

# Of the research-only signals, what was the outcome?
print(f"\n  Research-only signals trade outcomes (the trades z>1.5 kills):")
r_only_dates = qd.loc[full_mask][r_only].index
if len(r_only_dates) > 0:
    for d in r_only_dates:
        idx = qd.index.get_loc(d)
        if idx + 1 < len(qd):
            entry = float(qd["Close"].iloc[idx])
            # Simulate the trade outcome
            end_idx = min(idx + 6, len(qd) - 1)
            exit_idx = idx + 1
            stop = entry * 0.98
            tgt = entry * 1.05
            outcome = "time"
            exit_price = float(qd["Close"].iloc[end_idx])
            for j in range(idx + 1, end_idx + 1):
                p = float(qd["Close"].iloc[j])
                if p <= stop:
                    exit_price = stop
                    outcome = "stop"
                    break
                elif p >= tgt:
                    exit_price = tgt
                    outcome = "target"
                    break
                exit_price = p
            ret = (exit_price - entry) / entry
            print(f"    {d.date()}: entry={entry:.2f} exit={exit_price:.2f} "
                  f"({outcome}) ret={ret:+.2%}")
else:
    print("    (none)")

print(f"\n  Done. Review complete.")
