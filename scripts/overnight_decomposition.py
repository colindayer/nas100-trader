"""ACTION #1 from the strategy atlas: does our momentum alpha live OVERNIGHT or INTRADAY?

    python scripts/overnight_decomposition.py

THE PUBLISHED CLAIM (Lou, Polk & Skouras 2019, JFE, "A Tug of War")
  Across 14 well-known strategies, abnormal profits are earned EITHER entirely overnight OR
  entirely intraday -- typically with OPPOSITE signs in the other period. For MOMENTUM
  specifically, they find essentially ALL of the abnormal return occurs OVERNIGHT.

WHY THIS MATTERS HERE
  The intraday research programme spent a month testing signals on the intraday leg -- the leg
  this literature says carries NEGATIVE momentum profits. If the claim holds on our data, that is
  not a coincidence with our null results; it is a candidate explanation for them.

THE DECOMPOSITION
    overnight_t = open_t  / close_{t-1} - 1      (the gap; position held through the close)
    intraday_t  = close_t / open_t      - 1      (the session; position held through the day)
    (1+overnight)(1+intraday) = 1 + close_to_close     <- verified exactly, see self-check

VALIDITY CHECK, RUN FIRST AND REPORTED HONESTLY
  LPS studied US EQUITIES, which genuinely close for 17.5 hours. Most instruments in this panel
  are 24-hour CFDs where the "daily open" is a broker rollover stamp, not a re-opening auction.
  If open_t == close_{t-1} for an instrument, its overnight return is mechanically ~0 and this
  test CANNOT be run on it. That is reported per instrument BEFORE any result is interpreted,
  so a structural artifact is never read as a finding.

SIGNAL
  The FROZEN portfolio's own signal: sign of the 252-day return, shifted one day. Not a new
  strategy -- the existing one, decomposed. Nothing here changes the strategy or the engine.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "reference" / "portfolio_D1.csv"
LOOKBACK = 252
FROZEN = ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]
ANN = 252


def load():
    d = pd.read_csv(PANEL, index_col=0, parse_dates=True).sort_index()
    syms = sorted({c.rsplit("_", 1)[0] for c in d.columns})
    op = d[[f"{s}_open" for s in syms]].copy(); op.columns = syms
    cl = d[[f"{s}_close" for s in syms]].copy(); cl.columns = syms
    return op.ffill(), cl.ffill(), syms


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(ANN)) if sd > 0 else float("nan")


def main():
    op, cl, syms = load()
    overnight = (op / cl.shift(1) - 1).replace([np.inf, -np.inf], np.nan)
    intraday = (cl / op - 1).replace([np.inf, -np.inf], np.nan)
    c2c = (cl / cl.shift(1) - 1).replace([np.inf, -np.inf], np.nan)

    # ---------------- validity: is there a real gap at all?
    print("=" * 96)
    print(" 0  VALIDITY -- does an overnight period EXIST for this instrument?")
    print("=" * 96)
    print(f"  {'symbol':<9}{'gap vol':>10}{'session vol':>13}{'gap share':>11}{'usable?':>10}")
    usable = []
    for s in syms:
        gv, iv = overnight[s].std(), intraday[s].std()
        share = gv / (gv + iv) if (gv + iv) > 0 else 0.0
        ok = share > 0.10
        if ok:
            usable.append(s)
        print(f"  {s:<9}{gv:>10.5f}{iv:>13.5f}{share:>11.1%}{('YES' if ok else 'no gap'):>10}")
    print(f"\n  usable for this test: {', '.join(usable) if usable else 'NONE'}")
    if not usable:
        print("  -> the panel is 24-hour instruments only. The LPS test cannot be run here.")
        return

    # ---------------- 1. raw buy-and-hold split
    print("\n" + "=" * 96)
    print(" 1  BUY-AND-HOLD: where does the raw return live?")
    print("=" * 96)
    print(f"  {'symbol':<9}{'overnight':>12}{'intraday':>12}{'total':>12}"
          f"{'ON Sharpe':>11}{'ID Sharpe':>11}")
    for s in usable:
        a, b, t = overnight[s].mean() * ANN, intraday[s].mean() * ANN, c2c[s].mean() * ANN
        print(f"  {s:<9}{a:>+12.2%}{b:>+12.2%}{t:>+12.2%}"
              f"{sharpe(overnight[s]):>11.2f}{sharpe(intraday[s]):>11.2f}")

    # ---------------- 2. THE TEST: the frozen signal, decomposed
    print("\n" + "=" * 96)
    print(" 2  THE FROZEN MOMENTUM SIGNAL, DECOMPOSED   (252d return sign, shifted 1d)")
    print("     LPS predict: momentum alpha is OVERNIGHT, and intraday is negative.")
    print("=" * 96)
    sig = np.sign(cl.pct_change(LOOKBACK)).shift(1)
    print(f"  {'symbol':<9}{'ON ann':>10}{'ID ann':>10}{'full ann':>10}"
          f"{'ON Shrp':>9}{'ID Shrp':>9}{'full Shrp':>11}{'LPS?':>7}")
    rows, on_leg, id_leg, full_leg = [], {}, {}, {}
    for s in usable:
        w = sig[s]
        ron, rid, rfu = (w * overnight[s]).dropna(), (w * intraday[s]).dropna(), (w * c2c[s]).dropna()
        on_leg[s], id_leg[s], full_leg[s] = ron, rid, rfu
        lps = (ron.mean() > 0) and (rid.mean() < ron.mean())
        rows.append({"symbol": s, "on_ann": ron.mean() * ANN, "id_ann": rid.mean() * ANN,
                     "full_ann": rfu.mean() * ANN, "on_sharpe": sharpe(ron),
                     "id_sharpe": sharpe(rid), "full_sharpe": sharpe(rfu), "lps_pattern": lps})
        print(f"  {s:<9}{ron.mean()*ANN:>+10.2%}{rid.mean()*ANN:>+10.2%}{rfu.mean()*ANN:>+10.2%}"
              f"{sharpe(ron):>9.2f}{sharpe(rid):>9.2f}{sharpe(rfu):>11.2f}"
              f"{('YES' if lps else '-'):>7}")

    # ---------------- 3. portfolio level, equal weight across the frozen universe
    fu = [s for s in FROZEN if s in usable]
    print("\n" + "=" * 96)
    print(f" 3  PORTFOLIO (equal weight, {len(fu)} frozen assets: {', '.join(fu)})")
    print("=" * 96)
    pon = pd.concat([on_leg[s] for s in fu], axis=1).mean(axis=1)
    pid = pd.concat([id_leg[s] for s in fu], axis=1).mean(axis=1)
    pfu = pd.concat([full_leg[s] for s in fu], axis=1).mean(axis=1)
    for lab, r in (("overnight only", pon), ("intraday only", pid), ("full close-to-close", pfu)):
        print(f"  {lab:<22} ann {r.mean()*ANN:>+7.2%}  vol {r.std()*np.sqrt(ANN):>6.2%}  "
              f"Sharpe {sharpe(r):>5.2f}  hit {(r>0).mean():>5.1%}")

    # ---------------- 4. the cost that decides it
    print("\n" + "=" * 96)
    print(" 4  WHAT WOULD KILL IT")
    print("=" * 96)
    n_days = len(pon)
    print(f"  An overnight-only book holds through EVERY close: {n_days} financing charges.")
    print(f"  It must clear the swap. At the FTMO swing rates on our own account, measure the")
    print(f"  real per-night cost before believing any number above -- this script does NOT")
    print(f"  charge swap, so the overnight Sharpe here is an UPPER BOUND.")
    print(f"  Intraday-only pays no swap but doubles the spread crossings.")

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "results" / "overnight_decomposition.csv", index=False)
    n_lps = int(out["lps_pattern"].sum())
    print("\n" + "=" * 96)
    print(f" LPS pattern (overnight positive AND above intraday) holds in "
          f"{n_lps} of {len(out)} usable instruments")
    print("=" * 96)

    # ponytail: the decomposition is the whole claim -- verify it is exact, not approximate
    chk = ((1 + overnight[usable]) * (1 + intraday[usable]) - 1 - c2c[usable]).abs().max().max()
    assert chk < 1e-9, f"decomposition does not reconcile, max error {chk:.2e}"
    print(f"\n  self-check OK: (1+ON)(1+ID) == 1+C2C exactly, max error {chk:.2e}")
    print(f"  written -> results/overnight_decomposition.csv")


if __name__ == "__main__":
    main()
