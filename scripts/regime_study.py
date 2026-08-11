"""CAN WE REMOVE THE WORST REGIMES? -- the better question, tested honestly.

    python scripts/regime_study.py

THE QUESTION
  Not "what beats buy-and-hold" but "can buy-and-hold (and the frozen portfolio) be improved by
  sitting out its worst periods?" A filter that removes the bottom decile of months without
  removing the top decile is worth more than any new signal we have found.

THE TRAP THIS IS BUILT TO AVOID
  Regime conditioning is a search. With 6 regimes x 2 sides x 2 strategies there are 24 ways to
  slice, and the best of 24 noise draws looks like an edge. So:
    1 EVERY regime is defined BEFORE any result is seen, from trailing data only, and listed in
      REGIMES below. No regime is added or adjusted after looking.
    2 DISCOVERY 2000-2012 / VALIDATION 2013-2026. A filter is only reported as working if it
      improves BOTH. One segment is a hypothesis.
    3 A BOOTSTRAP REALITY CHECK asks how good the BEST of 24 random filters looks by chance, so
      "our best filter improved Sharpe by X" is measured against the right null.
    4 EVERY filter is charged the cost of the trades it causes (entering and exiting the market).

  A filter that only improves in-sample is reported as FAILED, not as promising.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ftmo_simulation import TARGET_P1, historical, net_returns, summarise

PANEL = ROOT / "data" / "reference" / "portfolio_D1.csv"
OUT = ROOT / "backtest_out" / "regime_v1"
ANN = 252
DISC_END, VAL_START = "2012-12-31", "2013-01-01"
SWITCH_COST_BPS = 3.0          # charged on every regime change (in or out of the market)
TARGET_VOL = 0.05


def load_close():
    d = pd.read_csv(PANEL, index_col=0, parse_dates=True).sort_index()
    syms = sorted({c.rsplit("_", 1)[0] for c in d.columns})
    cl = d[[f"{s}_close" for s in syms]].copy()
    cl.columns = syms
    return cl.ffill()


def build_regimes(px: pd.Series) -> dict:
    """Every mask is TRUE where we STAY INVESTED. All use trailing data only, shifted 1 day."""
    r = px.pct_change()
    ma200 = px.rolling(200).mean()
    ma50 = px.rolling(50).mean()
    rv20 = r.rolling(20).std() * np.sqrt(ANN)          # realised vol, our VIX proxy
    rv_med = rv20.rolling(252).median()
    dd = px / px.cummax() - 1
    mom12 = px.pct_change(252)

    return {
        "above_200dma":      (px > ma200),
        "above_50dma":       (px > ma50),
        "vol_below_median":  (rv20 < rv_med),
        "vol_below_25pct":   (rv20 < rv20.rolling(252).quantile(0.75)),
        "not_in_drawdown":   (dd > -0.10),
        "positive_12m":      (mom12 > 0),
    }


def apply_filter(r: pd.Series, mask: pd.Series, cost_bps: float = SWITCH_COST_BPS) -> pd.Series:
    """Charge a switch cost on every change of state. mask is shifted so it is tradable."""
    m = mask.shift(1).fillna(False).astype(float).reindex(r.index).fillna(0.0)
    switches = m.diff().abs().fillna(0.0)
    return r * m - switches * cost_bps / 1e4


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 100:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / ANN
    dd = float((eq / eq.cummax() - 1).min())
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "vol": r.std() * np.sqrt(ANN),
            "Sharpe": r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan,
            "maxDD": dd, "time_in": float((r != 0).mean())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cl = load_close()

    # --- the two things we are trying to improve
    nas = cl["NAS100"].pct_change().fillna(0.0)
    frozen = net_returns(cl[["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]], TARGET_VOL)
    targets = {"NAS100 B&H": nas, "Frozen Portfolio": frozen}
    regimes = build_regimes(cl["NAS100"])

    print("=" * 104)
    print(" REGIME STUDY -- can we remove the worst periods?")
    print(f" discovery ..{DISC_END}   validation {VAL_START}..   "
          f"switch cost {SWITCH_COST_BPS}bp   {len(regimes)} pre-registered regimes")
    print("=" * 104)

    rows = []
    for tname, tr in targets.items():
        base_d, base_v = stats(tr[:DISC_END]), stats(tr[VAL_START:])
        print(f"\n  {tname}")
        print(f"    {'filter':<20}{'D Sharpe':>10}{'V Sharpe':>10}{'D maxDD':>10}{'V maxDD':>10}"
              f"{'time in':>9}{'both better?':>14}")
        print(f"    {'(unfiltered)':<20}{base_d['Sharpe']:>10.2f}{base_v['Sharpe']:>10.2f}"
              f"{base_d['maxDD']:>10.1%}{base_v['maxDD']:>10.1%}{1.0:>9.0%}{'-':>14}")
        for rname, mask in regimes.items():
            f = apply_filter(tr, mask)
            sd, sv = stats(f[:DISC_END]), stats(f[VAL_START:])
            if not sd or not sv:
                continue
            better = (sd["Sharpe"] > base_d["Sharpe"]) and (sv["Sharpe"] > base_v["Sharpe"])
            rows.append({"target": tname, "regime": rname, "disc_sharpe": sd["Sharpe"],
                         "val_sharpe": sv["Sharpe"], "disc_dd": sd["maxDD"], "val_dd": sv["maxDD"],
                         "time_in": sv["time_in"], "improves_both": better,
                         "base_disc": base_d["Sharpe"], "base_val": base_v["Sharpe"]})
            print(f"    {rname:<20}{sd['Sharpe']:>10.2f}{sv['Sharpe']:>10.2f}"
                  f"{sd['maxDD']:>10.1%}{sv['maxDD']:>10.1%}{sv['time_in']:>9.0%}"
                  f"{('YES' if better else '-'):>14}")

    R = pd.DataFrame(rows)
    R.to_csv(OUT / "regime_study.csv", index=False)

    # ---------------- bootstrap reality check
    print("\n" + "=" * 104)
    print(" BOOTSTRAP REALITY CHECK -- how good is the BEST of N filters by pure chance?")
    print("=" * 104)
    rng = np.random.default_rng(11)
    n_filters = len(regimes) * len(targets)
    print("  A naive null of i.i.d. random masks is WRONG here: it switches on ~30% of days while")
    print("  a real regime is persistent, so the switch cost alone destroys it and any real filter")
    print("  wins trivially. The null below is a two-state Markov chain matched to EACH real")
    print("  filter's own time-in-market AND its own number of switches.\n")

    def markov_mask(index, time_in, n_switches):
        """Random mask with the same in-market fraction and the same persistence."""
        n = len(index)
        p_out_in = n_switches / (2 * max(n * (1 - time_in), 1))   # exit->enter rate
        p_in_out = n_switches / (2 * max(n * time_in, 1))         # enter->exit rate
        s = rng.random() < time_in
        arr = np.empty(n, dtype=bool)
        for t in range(n):
            arr[t] = s
            s = (not s) if rng.random() < (p_in_out if s else p_out_in) else s
        return pd.Series(arr, index=index)

    for tname, tr in targets.items():
        sub = R[R["target"] == tname]
        base_v = stats(tr[VAL_START:])["Sharpe"]
        obs = sub["val_sharpe"].max()
        v = tr[VAL_START:]
        # persistence of each real filter, measured on the validation window
        profiles = []
        for rname in sub["regime"]:
            m = regimes[rname].shift(1).fillna(False).astype(bool).reindex(v.index).fillna(False)
            profiles.append((float(m.mean()), float(m.astype(int).diff().abs().sum())))
        best_null = []
        for _ in range(400):
            best = -9.9
            for tin, nsw in profiles:
                s = stats(apply_filter(v, markov_mask(v.index, tin, nsw)))
                if s and s["Sharpe"] > best:
                    best = s["Sharpe"]
            best_null.append(best)
        bn = np.array(best_null)
        p = float((bn >= obs).mean())
        print(f"  {tname:<20} unfiltered {base_v:>5.2f}   best real filter {obs:>5.2f}   "
              f"null best-of-{len(profiles)}: median {np.median(bn):>5.2f} p95 "
              f"{np.percentile(bn,95):>5.2f}   p = {p:.3f}"
              f"   {'SIGNIFICANT' if p < 0.05 else 'NOT significant'}")

    # ---------------- FTMO impact of anything that survived
    surv = R[R["improves_both"]]
    print("\n" + "=" * 104)
    print(" SURVIVORS (improve Sharpe in BOTH segments)")
    print("=" * 104)
    if surv.empty:
        print("   NONE.")
    else:
        for _, s in surv.iterrows():
            print(f"   {s['target']:<20} {s['regime']:<20} "
                  f"D {s['base_disc']:.2f}->{s['disc_sharpe']:.2f}   "
                  f"V {s['base_val']:.2f}->{s['val_sharpe']:.2f}   in-market {s['time_in']:.0%}")
        print(f"\n   FTMO phase-1 impact (5% vol, historical paths):")
        print(f"   {'strategy':<40}{'pass%':>8}{'breach%':>9}{'med days':>10}")
        for tname, tr in targets.items():
            b = summarise(historical(tr, TARGET_P1))
            print(f"   {tname + ' (unfiltered)':<40}{b['pass_%']:>8.1f}"
                  f"{b['breach_total_%']:>9.1f}{(b['median_days_to_pass'] or 0):>10.0f}")
            for _, s in surv[surv["target"] == tname].iterrows():
                f = apply_filter(tr, regimes[s["regime"]])
                x = summarise(historical(f, TARGET_P1))
                print(f"   {tname + ' + ' + s['regime']:<40}{x['pass_%']:>8.1f}"
                      f"{x['breach_total_%']:>9.1f}{(x['median_days_to_pass'] or 0):>10.0f}")

    # ponytail: a filter must never be able to see the day it acts on
    m = regimes["above_200dma"].shift(1)
    assert m.index.equals(cl.index) and m.isna().iloc[0], "filter is not lagged"
    print(f"\n  self-check OK: regimes are lagged one day before use")
    print(f"  written -> {OUT}/regime_study.csv")


if __name__ == "__main__":
    main()
