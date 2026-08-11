"""OVERNIGHT STRATEGY -- COMPLETE EVALUATION AGAINST A FROZEN DEFINITION.

    python scripts/overnight_evaluation.py

THE HYPOTHESIS IS FROZEN BEFORE THIS RUNS. Nothing below is tuned, and no variant is searched.
The definition is exactly what `overnight_decomposition.py` measured, transcribed verbatim:

    universe    AUDUSD GOLD NAS100 SILVER SP500 USDCHF USDJPY
                -- chosen by overnight-leg Sharpe > 0 on 2000-2012 ONLY, so 2013-2026 is
                   genuinely out of sample and is reported separately below.
    signal      sign(close.pct_change(252)).shift(1)      [the frozen portfolio's own signal]
    holding     enter at each close, exit at the next open. THE OVERNIGHT LEG ONLY.
    weighting   equal weight across the 7, then scaled to a volatility target
    costs       spread charged per round trip + financing charged per night held

WHY THIS IS THE RIGHT ORDER
  The measured effect (OOS Sharpe 0.63 at 5.24% vol) is knife-edge against costs -- breakeven is
  1.32 bps per round trip and the book turns over completely 252 times a year. Optimising before
  costing would tune a strategy that may already be dead. So: cost it, simulate the prop rules,
  compare against the two incumbents, and only then decide whether optimisation is warranted.

FINANCING IS THE UNRESOLVED INPUT
  An overnight-only book pays financing on EVERY night. The real per-night rate is a property of
  the FTMO account and can only be read from MT5 (`symbol_info().swap_long/swap_short`), which is
  Windows-only and lives on the VPS. It is therefore swept across a range here and reported as a
  SENSITIVITY, not assumed. Any conclusion that flips inside the swept range is reported as
  undecided rather than resolved in the strategy's favour.

COMPARISON SET
  1 Frozen Portfolio   the production strategy, via its own production code path
  2 NAS100 buy & hold  the benchmark that beat everything we built last month
  3 Overnight          this hypothesis
  All three are volatility-targeted to the SAME grid so the comparison is not a leverage artifact.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ftmo_simulation import (MAX_DAYS, TARGET_P1, historical, net_returns,
                                     stationary_bootstrap, summarise)

OUT = ROOT / "backtest_out" / "overnight_v1"
PANEL = ROOT / "data" / "reference" / "portfolio_D1.csv"
ANN = 252

# ---------------------------------------------------------------- THE FREEZE
UNIVERSE = ["AUDUSD", "GOLD", "NAS100", "SILVER", "SP500", "USDCHF", "USDJPY"]
LOOKBACK = 252
SELECTION_END = "2012-12-31"          # universe chosen on data up to here, nothing after
OOS_START = "2013-01-01"
SPREAD_BPS_RT = 1.0                   # central assumption, swept below
FINANCING_BPS_NIGHT = 0.0             # UNKNOWN until read from MT5. Swept below.
VOL_GRID = [0.04, 0.05, 0.06, 0.08]

FREEZE = {"universe": UNIVERSE, "lookback": LOOKBACK, "signal": "sign(pct_change(252)).shift(1)",
          "holding": "close_t-1 -> open_t (overnight leg only)", "weighting": "equal, vol-targeted",
          "selection_window": f"..{SELECTION_END}", "oos_start": OOS_START}
FREEZE_HASH = hashlib.sha256(json.dumps(FREEZE, sort_keys=True).encode()).hexdigest()[:16]


def load_panel():
    d = pd.read_csv(PANEL, index_col=0, parse_dates=True).sort_index()
    syms = sorted({c.rsplit("_", 1)[0] for c in d.columns})
    op = d[[f"{s}_open" for s in syms]].copy(); op.columns = syms
    cl = d[[f"{s}_close" for s in syms]].copy(); cl.columns = syms
    return op.ffill(), cl.ffill()


def overnight_legs(op, cl):
    """Per-instrument overnight P&L of the frozen signal, BEFORE costs and BEFORE vol targeting."""
    sig = np.sign(cl.pct_change(LOOKBACK)).shift(1)
    on = (op / cl.shift(1) - 1)
    idl = (cl / op - 1)
    return (sig[UNIVERSE] * on[UNIVERSE]), (sig[UNIVERSE] * idl[UNIVERSE]), sig[UNIVERSE]


def vol_target(r: pd.Series, target: float, look: int = 60, max_lev: float = 3.0) -> pd.Series:
    """Scale to a volatility target using ONLY trailing information."""
    rv = r.rolling(look).std().shift(1) * np.sqrt(ANN)
    lev = (target / rv).clip(upper=max_lev).fillna(0.0)
    return (lev * r).dropna(), lev


def metrics(r: pd.Series, label: str, turnover_per_day: float = np.nan) -> dict:
    r = r.dropna()
    if len(r) < ANN:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / ANN
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(ANN)
    dn = r[r < 0].std() * np.sqrt(ANN)
    dd = float((eq / eq.cummax() - 1).min())
    return {"label": label, "years": yrs, "CAGR": cagr, "vol": vol,
            "Sharpe": r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan,
            "Sortino": r.mean() * ANN / dn if dn > 0 else np.nan,
            "maxDD": dd, "Calmar": cagr / abs(dd) if dd < 0 else np.nan,
            "hit_rate": float((r > 0).mean()), "turnover_per_day": turnover_per_day,
            "best_day": float(r.max()), "worst_day": float(r.min())}


def show(m: dict):
    print(f"  {m['label']:<22}{m['CAGR']:>8.2%}{m['vol']:>8.2%}{m['Sharpe']:>8.2f}"
          f"{m['Sortino']:>9.2f}{m['maxDD']:>9.2%}{m['Calmar']:>8.2f}{m['hit_rate']:>8.1%}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print(f" OVERNIGHT STRATEGY -- FROZEN EVALUATION      freeze hash {FREEZE_HASH}")
    print("=" * 100)
    for k, v in FREEZE.items():
        print(f"   {k:<18} {v}")

    op, cl = load_panel()
    on_i, id_i, sig = overnight_legs(op, cl)

    # gross equal-weight legs
    on_ew = on_i.mean(axis=1).dropna()
    id_ew = id_i.mean(axis=1).dropna()
    full_ew = (on_i + id_i + on_i * id_i).mean(axis=1).dropna()

    # turnover: the overnight book is fully entered and fully exited EVERY day
    turn_per_day = 2.0
    print(f"\n   turnover           {turn_per_day:.1f} x notional per day "
          f"({turn_per_day*ANN:.0f}x/yr)  -- full entry AND exit daily")
    print(f"   avg holding time   1 night (~17.5h calendar, 0 trading-day sessions)")

    # ---------------------------------------------------------------- 1. legs
    print("\n" + "=" * 100)
    print(" 1  CONTRIBUTION BY LEG (gross, equal weight, full sample)")
    print("=" * 100)
    print(f"  {'leg':<22}{'CAGR':>8}{'vol':>8}{'Sharpe':>8}{'Sortino':>9}{'maxDD':>9}"
          f"{'Calmar':>8}{'hit':>8}")
    for lab, r in (("overnight only", on_ew), ("intraday only", id_ew), ("full day", full_ew)):
        m = metrics(r, lab)
        if m:
            show(m)

    # ---------------------------------------------------------------- 2. by instrument
    print("\n" + "=" * 100)
    print(" 2  CONTRIBUTION BY INSTRUMENT (overnight leg, gross)")
    print("=" * 100)
    print(f"  {'symbol':<10}{'full ann':>10}{'is ann':>10}{'oos ann':>10}"
          f"{'full Shrp':>11}{'oos Shrp':>10}{'share of P&L':>14}")
    tot = on_i.sum().sum()
    for s in UNIVERSE:
        x = on_i[s].dropna()
        xi, xo = x[:SELECTION_END], x[OOS_START:]
        print(f"  {s:<10}{x.mean()*ANN:>+10.2%}{xi.mean()*ANN:>+10.2%}{xo.mean()*ANN:>+10.2%}"
              f"{x.mean()/x.std()*np.sqrt(ANN):>11.2f}"
              f"{xo.mean()/xo.std()*np.sqrt(ANN):>10.2f}{x.sum()/tot:>14.1%}")

    # ---------------------------------------------------------------- 3. costs
    print("\n" + "=" * 100)
    print(" 3  COST SENSITIVITY -- spread x financing   (net Sharpe, OUT OF SAMPLE 2013-2026)")
    print("=" * 100)
    oos = on_ew[OOS_START:]
    print(f"   gross OOS: {oos.mean()*ANN:+.2%}/yr  vol {oos.std()*np.sqrt(ANN):.2%}  "
          f"Sharpe {oos.mean()/oos.std()*np.sqrt(ANN):.2f}")
    fin_grid = [0.0, 0.25, 0.5, 1.0, 2.0]
    spr_grid = [0.0, 0.5, 1.0, 1.5, 2.0]
    print(f"\n   {'':<14}" + "".join(f"{'fin ' + str(f) + 'bp':>12}" for f in fin_grid))
    grid = {}
    for sp in spr_grid:
        cells = []
        for fn in fin_grid:
            net = oos - (sp + fn) / 1e4
            sh = net.mean() / net.std() * np.sqrt(ANN)
            grid[(sp, fn)] = sh
            cells.append(f"{sh:>12.2f}")
        print(f"   spread {sp:<5.1f}bp" + "".join(cells))
    alive = sum(1 for v in grid.values() if v > 0)
    print(f"\n   positive net Sharpe in {alive} of {len(grid)} cost cells")
    print(f"   NOTE: financing is charged EVERY night on full notional. The true rate is a")
    print(f"   property of the FTMO account and is NOT known here -- it must be read from MT5.")

    # ---------------------------------------------------------------- 4. yearly
    print("\n" + "=" * 100)
    print(f" 4  YEARLY RETURNS (net at spread {SPREAD_BPS_RT}bp, financing 0bp -- UPPER BOUND)")
    print("=" * 100)
    net = on_ew - SPREAD_BPS_RT / 1e4
    yr = net.groupby(net.index.year).apply(lambda x: (1 + x).prod() - 1)
    for y, v in yr.items():
        tag = " (OOS)" if y >= 2013 else ""
        print(f"   {y}  {v:>+8.2%}{tag}")

    # ---------------------------------------------------------------- 5. walk-forward
    print("\n" + "=" * 100)
    print(" 5  WALK-FORWARD STABILITY (net, rolling 3y non-overlapping)")
    print("=" * 100)
    for start in range(2000, 2026, 3):
        w = net[f"{start}-01-01":f"{start+2}-12-31"]
        if len(w) < 200:
            continue
        print(f"   {start}-{start+2}  ann {w.mean()*ANN:>+7.2%}  vol {w.std()*np.sqrt(ANN):>6.2%}"
              f"  Sharpe {w.mean()/w.std()*np.sqrt(ANN):>6.2f}")

    # ---------------------------------------------------------------- 6. parameter sensitivity
    print("\n" + "=" * 100)
    print(" 6  PARAMETER SENSITIVITY -- lookback (NOT optimised, reported only)")
    print("=" * 100)
    onr = (op / cl.shift(1) - 1)[UNIVERSE]
    for lb in (63, 126, 189, 252, 378, 504):
        sg = np.sign(cl[UNIVERSE].pct_change(lb)).shift(1)
        r = (sg * onr).mean(axis=1).dropna() - SPREAD_BPS_RT / 1e4
        ro = r[OOS_START:]
        print(f"   lookback {lb:>4}d   full Sharpe {r.mean()/r.std()*np.sqrt(ANN):>6.2f}"
              f"   OOS Sharpe {ro.mean()/ro.std()*np.sqrt(ANN):>6.2f}"
              f"   {'<-- FROZEN' if lb == LOOKBACK else ''}")

    # ---------------------------------------------------------------- 7. THREE-WAY
    print("\n" + "=" * 100)
    print(" 7  THREE-WAY COMPARISON, all volatility-targeted to the SAME grid")
    print("=" * 100)
    px = cl.copy()
    nas = px["NAS100"].pct_change().fillna(0.0)

    results = {}
    for tv in VOL_GRID:
        on_t, _ = vol_target(on_ew - SPREAD_BPS_RT / 1e4, tv)
        bh_t, _ = vol_target(nas, tv)
        fz = net_returns(px[["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]], tv)
        results[tv] = {"Overnight": on_t, "NAS100 B&H": bh_t, "Frozen Portfolio": fz}

    for tv in VOL_GRID:
        print(f"\n   --- target vol {tv:.0%} " + "-" * 70)
        print(f"  {'strategy':<22}{'CAGR':>8}{'vol':>8}{'Sharpe':>8}{'Sortino':>9}"
              f"{'maxDD':>9}{'Calmar':>8}{'hit':>8}")
        for name, r in results[tv].items():
            m = metrics(r, name)
            if m:
                show(m)

    # ---------------------------------------------------------------- 8. FTMO
    print("\n" + "=" * 100)
    print(" 8  FTMO SIMULATION -- phase 1 (+10% / -10% total / -5% daily)")
    print("     historical = every start date (overlapping). bootstrap = stationary, block 20d.")
    print("=" * 100)
    rows = []
    for tv in VOL_GRID:
        print(f"\n   --- target vol {tv:.0%} " + "-" * 70)
        print(f"  {'strategy':<22}{'method':<12}{'pass%':>8}{'brch tot%':>11}"
              f"{'brch day%':>11}{'timeout%':>10}{'med days':>10}")
        for name, r in results[tv].items():
            for meth, res in (("historical", historical(r, TARGET_P1)),
                              ("bootstrap", stationary_bootstrap(r, TARGET_P1, n=2000))):
                s = summarise(res)
                rows.append({"target_vol": tv, "strategy": name, "method": meth, **s})
                md = s["median_days_to_pass"]
                print(f"  {name:<22}{meth:<12}{s['pass_%']:>8.1f}{s['breach_total_%']:>11.1f}"
                      f"{s['breach_daily_%']:>11.1f}{s['timeout_%']:>10.1f}"
                      f"{(md if md else 0):>10.0f}")

    pd.DataFrame(rows).to_csv(OUT / "ftmo_three_way.csv", index=False)
    json.dump({"freeze": FREEZE, "freeze_hash": FREEZE_HASH},
              open(OUT / "FREEZE.json", "w"), indent=1)

    # ponytail: the decomposition underpins every number here -- verify it still reconciles
    chk = ((1 + (op / cl.shift(1) - 1)[UNIVERSE]) * (1 + (cl / op - 1)[UNIVERSE])
           - (cl / cl.shift(1))[UNIVERSE]).abs().max().max()
    assert chk < 1e-9, f"leg decomposition broken, max error {chk:.2e}"
    print(f"\n  self-check OK: legs reconcile to close-to-close, max error {chk:.2e}")
    print(f"  written -> {OUT}/")


if __name__ == "__main__":
    main()
