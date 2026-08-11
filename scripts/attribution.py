"""Decompose the baseline. WHERE does Sharpe 0.363 come from, and what is destroying it?

    python scripts/attribution.py                       # per-asset attribution (no re-runs)
    python scripts/attribution.py --loo                 # + leave-one-out (13 re-runs, slow)

Every number is computed from the artifacts the baseline already wrote -- weights.csv and the
price panel -- so nothing is re-simulated and nothing can drift from the run being explained.

  contribution_i(t) = w_i(t) * r_i(t)              return contribution, exact and additive
  cost_i(t)         = |dw_i(t)| * 3bps             cost attribution, exact and additive
  MCTR_i            = w_i * (Sigma w)_i / sigma_p  marginal contribution to portfolio RISK

MCTR is the one that matters and the one that gets skipped: an asset can have a positive return
contribution and still destroy Sharpe by adding more risk than return. Sum(MCTR) = sigma_p
exactly, so the split is a real decomposition, not a heuristic.

No optimisation here. No parameters change. This only says where the existing number came from.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "backtest_out" / "reference_funded_full_TREND"
REFERENCE = ROOT / "data" / "reference"
COST_BPS = 3.0

GROUPS = {
    "FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"],
    "METALS": ["GOLD", "SILVER", "COPPER"],
    "ENERGY": ["OIL"],
    "INDICES": ["NAS100", "SP500"],
}


def load_panel():
    p = REFERENCE / "portfolio_D1.csv"
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    cols = {c.rsplit("_", 1)[0]: c for c in d.columns if c.endswith("_close")}
    out = d[list(cols.values())]
    out.columns = list(cols.keys())
    return out.sort_index()


def maxdd(series_ret):
    eq = (1 + series_ret).cumprod()
    return float((eq / eq.cummax() - 1).min())


def main(loo: bool):
    W = pd.read_csv(ART / "weights.csv", index_col=0, parse_dates=True)
    eqc = pd.read_csv(ART / "equity_curve.csv", index_col=0, parse_dates=True)
    # must reproduce the backtest's own preparation exactly: ffill, then drop rows where ANY
    # symbol is missing, THEN take returns. Reindexing to W afterwards changes the return series
    # at gaps and makes the decomposition fail to reconcile.
    full = load_panel().ffill().dropna(how="any")[list(W.columns)]
    ret = full.pct_change().fillna(0.0).reindex(W.index)
    close = full

    contrib = W * ret                                   # additive: sums to gross_return
    dW = W.diff().fillna(W.iloc[0])
    costs = dW.abs() * COST_BPS / 1e4
    net_c = contrib - costs
    yrs = len(W) / 252.0

    chk = float((contrib.sum(axis=1) - eqc["gross_return"]).abs().max())
    print(f"decomposition check: max |sum(contrib) - gross_return| = {chk:.2e} "
          f"({'EXACT' if chk < 1e-10 else 'MISMATCH — do not trust the split'})")

    # ---- risk decomposition from the REALISED contribution series.
    # Using mean weights throws away all the time variation that the strategy is made of, and
    # produces near-zero denominators that make any ratio meaningless. cov(contrib_i, port)/
    # var(port) is additive, sums to exactly 1, and needs no assumption about constant weights.
    port = net_c.sum(axis=1)
    var_p = float(port.var())
    risk_share = net_c.apply(lambda c: c.cov(port) / var_p)
    sig_p = float(port.std() * np.sqrt(252))
    mctr = risk_share * sig_p

    rows = []
    for s in W.columns:
        r = net_c[s]
        rows.append({
            "symbol": s,
            "ann_return_contrib": float(r.sum() / yrs),
            "total_return_contrib": float(r.sum()),
            "gross_contrib": float(contrib[s].sum()),
            "cost_total": float(costs[s].sum()),
            "cost_share_%": float(costs[s].sum() / costs.sum().sum() * 100),
            "turnover_share_%": float(dW[s].abs().sum() / dW.abs().sum().sum() * 100),
            "vol_of_contrib": float(r.std() * np.sqrt(252)),
            "MCTR": float(mctr[s]),
            "risk_share_%": float(mctr[s] / sig_p * 100),
            "standalone_sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else np.nan,
            "maxdd_of_contrib": maxdd(r),
            "avg_abs_weight": float(W[s].abs().mean()),
        })
    A = pd.DataFrame(rows).set_index("symbol")
    # ratio-to-risk is only meaningful where the asset actually carries risk; below 2% of
    # portfolio variance the denominator is noise and the ratio is not reported.
    A["return_per_unit_risk"] = np.where(A["risk_share_%"].abs() >= 2.0,
                                         A["ann_return_contrib"] / A["MCTR"], np.nan)
    A = A.sort_values("ann_return_contrib", ascending=False)

    pd.set_option("display.width", 200)
    print("\n" + "=" * 100)
    print(" PER-ASSET ATTRIBUTION  (net of costs; ann_return_contrib sums to portfolio CAGR-ish)")
    print("=" * 100)
    show = A[["ann_return_contrib", "cost_total", "cost_share_%", "turnover_share_%",
              "MCTR", "risk_share_%", "standalone_sharpe", "return_per_unit_risk",
              "maxdd_of_contrib", "avg_abs_weight"]]
    print(show.to_string(float_format=lambda x: f"{x:9.4f}"))

    print(f"\n  portfolio vol (from mean weights): {sig_p:.4f}   sum(MCTR) = {mctr.sum():.4f}")
    print(f"  total net contribution/yr: {A['ann_return_contrib'].sum():.4f}")

    print("\n" + "=" * 100)
    print(" BY GROUP")
    print("=" * 100)
    grows = []
    for g, syms in GROUPS.items():
        syms = [s for s in syms if s in W.columns]
        r = net_c[syms].sum(axis=1)
        grows.append({"group": g, "n": len(syms),
                      "ann_return": float(r.sum() / yrs),
                      "vol": float(r.std() * np.sqrt(252)),
                      "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else np.nan,
                      "maxdd": maxdd(r),
                      "risk_share_%": float(mctr[syms].sum() / sig_p * 100),
                      "cost_share_%": float(costs[syms].sum().sum() / costs.sum().sum() * 100)})
    G = pd.DataFrame(grows).set_index("group").sort_values("ann_return", ascending=False)
    print(G.to_string(float_format=lambda x: f"{x:9.4f}"))

    print("\n" + "=" * 100)
    print(" BY YEAR, BY GROUP  (net contribution)")
    print("=" * 100)
    ann = pd.DataFrame({g: net_c[[s for s in sy if s in W.columns]].sum(axis=1)
                        for g, sy in GROUPS.items()})
    ann["TOTAL"] = net_c.sum(axis=1)
    print(ann.groupby(ann.index.year).sum().to_string(float_format=lambda x: f"{x:8.3f}"))

    print("\n" + "=" * 100)
    print(" RANKED — most to least valuable (net return per unit of risk added)")
    print("=" * 100)
    rank = A.sort_values("ann_return_contrib", ascending=False)
    for i, (s, r) in enumerate(rank.iterrows(), 1):
        rr = r["return_per_unit_risk"]
        rr_s = f"{rr:+7.3f}" if np.isfinite(rr) else "      -"
        verdict = ("pays for its risk" if r["ann_return_contrib"] > 0 and
                   r["risk_share_%"] < 2 * max(r["ann_return_contrib"] / max(
                       A["ann_return_contrib"].sum(), 1e-9) * 100, 1e-9) else
                   "positive" if r["ann_return_contrib"] > 0 else
                   "NEGATIVE return contribution")
        print(f"  {i:>2}. {s:<8} ret/yr {r['ann_return_contrib']:+7.4f}  "
              f"risk {r['risk_share_%']:5.1f}%  cost {r['cost_share_%']:5.1f}%  "
              f"r/risk {rr_s}   {verdict}")

    A.to_csv(ART / "attribution_by_asset.csv")
    G.to_csv(ART / "attribution_by_group.csv")
    ann.groupby(ann.index.year).sum().to_csv(ART / "attribution_by_year_group.csv")
    net_c.to_csv(ART / "contribution_daily.csv")
    print(f"\n  written -> {ART}/attribution_by_asset.csv, _by_group.csv, "
          f"_by_year_group.csv, contribution_daily.csv")

    if loo:
        print("\n" + "=" * 100)
        print(" LEAVE-ONE-OUT — rerunning the PRODUCTION function with each symbol removed")
        print(" (no parameters change; the universe changes, so weights renormalise as they would live)")
        print("=" * 100)
        from scripts.portfolio_mt5 import CONFIGS, target_weights
        cfg = dict(CONFIGS["funded"]); cfg["sleeves"] = ("TREND",)
        base = None
        out = []
        for drop in [None] + list(W.columns):
            cols = [c for c in W.columns if c != drop]
            px = close[cols].dropna(how="any")
            r2 = px.pct_change().fillna(0.0)
            prev = pd.Series(0.0, index=cols)
            nets = []
            for i in range(300, len(px)):
                w, _ = target_weights(px.iloc[:i], carry_signs={}, **cfg)
                w = w.reindex(cols).fillna(0.0)
                g = float((w * r2.iloc[i]).sum())
                c = float((w - prev).abs().sum()) * COST_BPS / 1e4
                nets.append(g - c)
                prev = w
            n = pd.Series(nets, index=px.index[300:])
            sh = float(n.mean() / n.std() * np.sqrt(252))
            dd = maxdd(n)
            if drop is None:
                base = (sh, dd)
                print(f"  {'BASELINE':<10} sharpe {sh:6.3f}  maxDD {dd:7.2%}")
            else:
                out.append({"removed": drop, "sharpe": sh, "d_sharpe": sh - base[0],
                            "maxdd": dd, "d_maxdd": dd - base[1]})
                print(f"  drop {drop:<8} sharpe {sh:6.3f} ({sh-base[0]:+.3f})   "
                      f"maxDD {dd:7.2%} ({dd-base[1]:+.2%})   "
                      f"{'REMOVING HELPS' if sh > base[0] else ''}")
        L = pd.DataFrame(out).sort_values("d_sharpe", ascending=False)
        L.to_csv(ART / "leave_one_out.csv", index=False)
        print(f"\n  written -> {ART}/leave_one_out.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loo", action="store_true")
    main(ap.parse_args().loo)
