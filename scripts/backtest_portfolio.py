"""The FIRST real backtest of portfolio_multisleeve. Run on the VPS, where the data is.

    py scripts\\backtest_portfolio.py --config funded
    py scripts\\backtest_portfolio.py --config funded --sleeves TREND

WHY THIS EXISTS
---------------
Nothing ever produced this strategy's historical performance numbers. `wf_2012_2026`
("Sharpe 0.62 active period 2012-2026, 17/22 positive years, maxDD -18.8%") is a hand-typed
string in registry/belief_v2.json, added by a promotion-plumbing commit that contained no
backtest, no equity curve and no trade list. The contract's only approved trial,
TR-a921975d8eef2571, is a gold/silver-ratio study that was never run and was explicitly ruled
"may not be cited as evidence" on 2026-07-28. A max drawdown cannot exist without an equity
curve, and an equity curve needs entries, exits, sizing, portfolio state, rebalancing and PnL.
None were ever computed.

PARITY BY CONSTRUCTION
----------------------
This calls `portfolio_mt5.target_weights` -- the SAME function the live runner calls -- rather
than reimplementing it. A reimplementation would drift from production the moment either side
changed, and "the backtest and the bot disagree" is the failure this whole exercise exists to
prevent. Entries, exits and sizing are therefore identical to live by definition: the strategy
holds target weights, and its EXIT is the weight changing. There is no separate exit rule, and
adding one would make this a different strategy.

WHAT THIS CAN AND CANNOT MEASURE -- read before quoting any number
------------------------------------------------------------------
CAN:  close-to-close equity, Sharpe, per-year returns, close-based max drawdown, turnover and
      costs, for whichever sleeves the data can actually drive.

CANNOT, on daily closes alone:
  * INTRADAY drawdown. FTMO checks equity intraday against 10% total / 5% daily. A close-based
    DD understates the excursion that fails you. This is the defect already recorded as
    `prop_audit`: "daily-close DD measurement". Pass --intraday to use exported H1 bars.
  * Any stop-loss or take-profit. A stop fires intraday. Not modelled here because it is not in
    the strategy.

CANNOT, ever, with the data MT5 provides:
  * THE CARRY SLEEVE. carry_signs comes from live broker swap_long/swap_short. MT5 serves no
    history for swap rates, so the sign that was in force in 2015 is unknowable. The deployed
    `funded` config is TREND+CARRY, which means HALF OF IT IS NOT BACKTESTABLE on this data.
    This script runs the sleeves it can drive and says so; it does not silently pretend the
    carry sleeve was tested. Reconstructing carry from rate differentials would be new research.
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
from scripts.portfolio_mt5 import CONFIGS, target_weights          # PRODUCTION function

DATA = ROOT / "data" / "mt5"
REFERENCE = ROOT / "data" / "reference"      # 20y Yahoo series; see fetch_reference_history.py
COST_BPS_PER_SIDE = 3.0        # strategy_contracts/portfolio_multisleeve.json: "3bps/side"


def load(label: str, source: str = "mt5") -> pd.DataFrame | None:
    root = REFERENCE if source == "reference" else DATA
    for p in (root / f"portfolio_{label}.parquet", root / f"portfolio_{label}.csv"):
        if p.exists():
            d = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(
                p, index_col=0, parse_dates=True)
            return d
    return None


def field(panel: pd.DataFrame, name: str) -> pd.DataFrame:
    """Columns are '<SYMBOL>_<field>'. Pull one field for every symbol."""
    cols = {c.rsplit("_", 1)[0]: c for c in panel.columns if c.endswith(f"_{name}")}
    out = panel[list(cols.values())].copy()
    out.columns = list(cols.keys())
    return out.sort_index()


# Instruments listed at different times, so a fixed 13-symbol panel starts when the YOUNGEST one
# does. On FTMO that is COPPER at 2024-12-02 -- twenty months. Tiers report what each universe can
# actually support, instead of throwing away twenty years of FX history to keep copper.
TIERS = {
    "fx":        ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"],
    "fx_metals": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
                  "GOLD", "SILVER"],
    "fx_metals_idx": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
                      "GOLD", "SILVER", "NAS100", "SP500"],
    "plus_oil":  ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
                  "GOLD", "SILVER", "NAS100", "SP500", "OIL"],
    "full":      None,          # everything the export contains, incl. COPPER
}


def verify_window(close, cfg, window, n=12, seed=0):
    """Prove the trailing window reproduces full-expanding weights before trusting it for speed.

    target_weights uses pct_change(252), EWM span 60 and 252, and a 1764-bar rolling window. A
    truncated history is only legitimate if it returns the SAME weights; asserting that without
    checking is how a speed optimisation silently becomes a different strategy."""
    rng = np.random.default_rng(seed)
    lo = max(window + 10, 400)
    if len(close) <= lo + 5:
        return None
    idxs = sorted(rng.choice(range(lo, len(close)), size=min(n, len(close) - lo), replace=False))
    worst = 0.0
    for i in idxs:
        w_full, _ = target_weights(close.iloc[:i], carry_signs={}, **cfg)
        w_win, _ = target_weights(close.iloc[max(0, i - window):i], carry_signs={}, **cfg)
        a = w_full.reindex(close.columns).fillna(0.0)
        b = w_win.reindex(close.columns).fillna(0.0)
        worst = max(worst, float((a - b).abs().max()))
    return worst


def run(config: str, sleeves: tuple | None, warmup: int, intraday: bool,
        universe: str = "full", window: int = 2000, check: bool = True,
        source: str = "mt5"):
    panel = load("D1", source)
    if panel is None:
        raise SystemExit(f"no daily export found for source={source} — run export_history.py (mt5) or fetch_reference_history.py (reference)")
    close = field(panel, "close").ffill().dropna(how="all")
    if TIERS.get(universe):
        keep = [c for c in TIERS[universe] if c in close.columns]
        missing = [c for c in TIERS[universe] if c not in close.columns]
        if missing:
            print(f"  (universe '{universe}': {missing} absent from the export)")
        close = close[keep]
    close = close.dropna(how="any")      # the panel starts when EVERY member has data
    print(f"data: {close.shape[1]} symbols, {len(close):,} daily bars "
          f"{close.index[0].date()} -> {close.index[-1].date()}")

    # every symbol must be present for the cross-sectional sleeves to mean anything
    first_valid = close.apply(lambda s: s.first_valid_index())
    limiting = first_valid.idxmax()
    print(f"limiting symbol: {limiting} starts {first_valid.max().date()} — "
          f"the multi-asset backtest cannot begin before this")

    cfg = dict(CONFIGS[config])
    if sleeves:
        cfg["sleeves"] = tuple(sleeves)
    tested = tuple(s for s in cfg["sleeves"] if s != "CARRY")
    if "CARRY" in cfg["sleeves"]:
        print("\n  !! CARRY REQUESTED BUT NOT BACKTESTABLE: carry_signs comes from live broker "
              "swap rates,\n     which MT5 serves no history for. Running "
              f"{tested} only. The deployed '{config}' config is\n     "
              f"{tuple(cfg['sleeves'])}, so this validates PART of what is deployed, not all.")
    if not tested:
        raise SystemExit("nothing testable left after removing CARRY")
    cfg["sleeves"] = tested

    if check:
        err = verify_window(close, cfg, window)
        if err is None:
            print(f"\n  window check: sample too short — running full expanding history")
            window = 10 ** 9
        elif err > 1e-6:
            print(f"\n  !! window {window} does NOT reproduce full history (max weight diff "
                  f"{err:.2e}) — falling back to full expanding history (slower, exact)")
            window = 10 ** 9
        else:
            print(f"\n  window check: trailing {window} bars reproduce full-history weights "
                  f"(max diff {err:.2e}) — safe to use")

    ret = close.pct_change().fillna(0.0)
    rows, weights = [], []
    prev_w = pd.Series(0.0, index=close.columns)
    for i in range(warmup, len(close)):
        # EXPANDING window, strictly past data -> no look-ahead. carry_signs empty = sleeve off.
        w, _ = target_weights(close.iloc[max(0, i - window):i], carry_signs={}, **cfg)
        w = w.reindex(close.columns).fillna(0.0)
        gross_ret = float((w * ret.iloc[i]).sum())
        turnover = float((w - prev_w).abs().sum())
        cost = turnover * COST_BPS_PER_SIDE / 1e4
        rows.append({"date": close.index[i], "gross": gross_ret, "turnover": turnover,
                     "cost": cost, "net": gross_ret - cost})
        weights.append(w)
        prev_w = w

    d = pd.DataFrame(rows).set_index("date")
    eq = (1 + d["net"]).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(d) / 252.0
    sharpe = d["net"].mean() / d["net"].std() * np.sqrt(252) if d["net"].std() > 0 else float("nan")

    by_year = d.groupby(d.index.year)["net"].apply(lambda s: (1 + s).prod() - 1)
    pos = int((by_year > 0).sum())

    print("\n" + "=" * 74)
    print(f" BACKTEST — config={config} sleeves={tested} costs={COST_BPS_PER_SIDE}bps/side")
    print("=" * 74)
    print(f"  period          {d.index[0].date()} -> {d.index[-1].date()}  ({yrs:.1f} years)")
    print(f"  total return    {eq.iloc[-1] - 1:+.1%}")
    print(f"  CAGR            {eq.iloc[-1] ** (1 / yrs) - 1:+.2%}" if yrs > 0 else "")
    print(f"  volatility      {d['net'].std() * np.sqrt(252):.1%}")
    print(f"  SHARPE          {sharpe:.2f}")
    print(f"  MAX DD (close)  {dd.min():.1%}")
    print(f"  positive years  {pos}/{len(by_year)}")
    print(f"  turnover        {d['turnover'].mean():.3f}/day   costs "
          f"{d['cost'].sum() / yrs * 100:.2f}%/yr")

    print(f"\n  {'year':>6} {'net':>9}")
    for y, v in by_year.items():
        print(f"  {y:>6} {v:>+9.1%}")

    claim = {"sharpe": 0.62, "positive_years": "17/22", "maxdd": -0.188}
    print("\n" + "-" * 74)
    print(f"  THE CLAIM ON RECORD (wf_2012_2026, hand-typed, no artifact): "
          f"Sharpe {claim['sharpe']}, {claim['positive_years']} positive years, "
          f"maxDD {claim['maxdd']:.1%}")
    print(f"  THIS MEASUREMENT:                                            "
          f"Sharpe {sharpe:.2f}, {pos}/{len(by_year)} positive years, maxDD {dd.min():.1%}")
    print("  These are not the same test: the claim covers 2012-2026 with CARRY included.")
    print("-" * 74)

    if intraday:
        h1 = load("H1")
        if h1 is None:
            print("\n  --intraday requested but no H1 export found — skipped")
        else:
            print(f"\n  H1 export present: {len(h1):,} bars. Intraday drawdown modelling is the "
                  "next\n  step and is what FTMO's 10%/5% rules actually require.")

    # ---------- ARTIFACTS: the raw material, not a summary ----------
    art = ROOT / "backtest_out" / f"{source}_{config}_{universe}_{'_'.join(tested)}"
    art.mkdir(parents=True, exist_ok=True)

    W = pd.DataFrame(weights, index=d.index)
    eq_df = pd.DataFrame({"gross_return": d["gross"], "cost": d["cost"], "net_return": d["net"],
                          "equity": eq, "drawdown": dd, "turnover": d["turnover"]})
    eq_df.index.name = "date"
    eq_df.to_csv(art / "equity_curve.csv")
    eq_df[["net_return"]].to_csv(art / "daily_returns.csv")
    W.to_csv(art / "weights.csv")
    by_year.rename("net_return").to_csv(art / "yearly_returns.csv")

    dW = W.diff().fillna(W.iloc[0])
    log = (dW.stack().rename("delta_weight").reset_index()
             .rename(columns={"level_0": "date", "level_1": "symbol"}))
    log = log[log["delta_weight"].abs() > 1e-9].copy()
    log["target_weight"] = [W.at[r.date, r.symbol] for r in log.itertuples()]
    log["cost"] = log["delta_weight"].abs() * COST_BPS_PER_SIDE / 1e4
    log.to_csv(art / "rebalance_log.csv", index=False)

    m = eq_df["net_return"].resample("ME").apply(lambda x: (1 + x).prod() - 1)
    meq = (1 + m).cumprod()
    mdd = meq / meq.cummax() - 1
    pd.DataFrame({"monthly_return": m, "monthly_equity": meq,
                  "monthly_drawdown": mdd}).to_csv(art / "monthly.csv")

    roll = eq_df["net_return"].rolling(252).apply(lambda x: (1 + x).prod() - 1).dropna()
    stats = {
        "source": source, "config": config, "universe": universe,
        "symbols": list(close.columns), "sleeves_tested": list(tested),
        "carry_excluded": "CARRY" in CONFIGS[config]["sleeves"],
        "period_start": str(d.index[0].date()), "period_end": str(d.index[-1].date()),
        "years": round(yrs, 2), "n_days": int(len(d)),
        "total_return": round(float(eq.iloc[-1] - 1), 4),
        "cagr": round(float(eq.iloc[-1] ** (1 / yrs) - 1), 4),
        "volatility": round(float(d["net"].std() * np.sqrt(252)), 4),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown_close": round(float(dd.min()), 4),
        "max_drawdown_date": str(dd.idxmin().date()),
        "max_drawdown_monthly": round(float(mdd.min()), 4),
        "positive_years": f"{pos}/{len(by_year)}",
        "best_year": {str(by_year.idxmax()): round(float(by_year.max()), 4)},
        "worst_year": {str(by_year.idxmin()): round(float(by_year.min()), 4)},
        "best_12m_rolling": round(float(roll.max()), 4) if len(roll) else None,
        "worst_12m_rolling": round(float(roll.min()), 4) if len(roll) else None,
        "best_month": {str(m.idxmax().date()): round(float(m.max()), 4)},
        "worst_month": {str(m.idxmin().date()): round(float(m.min()), 4)},
        "avg_daily_turnover": round(float(d["turnover"].mean()), 4),
        "total_cost_pct": round(float(d["cost"].sum()) * 100, 3),
        "cost_pct_per_year": round(float(d["cost"].sum() / yrs) * 100, 3),
        "rebalance_rows": int(len(log)),
        "position_changes_per_year": round(len(log) / yrs, 1),
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "window": window if window < 10 ** 8 else "full_expanding",
        "code_sha256_portfolio_mt5": __import__("hashlib").sha256(
            (ROOT / "scripts" / "portfolio_mt5.py").read_bytes()).hexdigest()[:16],
        "data_sha256": __import__("hashlib").sha256(
            (REFERENCE if source == "reference" else DATA).joinpath(
                "portfolio_D1.csv").read_bytes()).hexdigest()[:16]
        if (REFERENCE if source == "reference" else DATA).joinpath("portfolio_D1.csv").exists()
        else None,
    }
    json.dump(stats, open(art / "statistics.json", "w"), indent=1)
    print(f"\n  ARTIFACTS -> {art}")
    for f in sorted(art.iterdir()):
        print(f"    {f.name:<22} {f.stat().st_size:>10,} bytes")

    out = ROOT / "registry" / f"backtest_{source}_{config}_{universe}_{'_'.join(tested)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"config": config, "source": source, "universe": universe, "symbols": list(close.columns),
               "window": window if window < 10 ** 8 else "full_expanding", "sleeves": list(tested),
               "period": [str(d.index[0].date()), str(d.index[-1].date())],
               "years": round(yrs, 2), "sharpe": round(float(sharpe), 3),
               "total_return": round(float(eq.iloc[-1] - 1), 4),
               "vol": round(float(d["net"].std() * np.sqrt(252)), 4),
               "max_dd_close": round(float(dd.min()), 4),
               "positive_years": f"{pos}/{len(by_year)}",
               "by_year": {int(k): round(float(v), 4) for k, v in by_year.items()},
               "cost_bps_per_side": COST_BPS_PER_SIDE,
               "carry_excluded": "CARRY" in CONFIGS[config]["sleeves"],
               "caveats": ["close-based DD understates intraday excursion (prop_audit defect)",
                           "CARRY sleeve not backtestable: no swap-rate history in MT5",
                           "no stop-loss or take-profit — the strategy has none"]},
              open(out, "w"), indent=1)
    print(f"\n  written: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="funded", choices=list(CONFIGS))
    ap.add_argument("--sleeves", nargs="*", default=None,
                    help="override the config's sleeves, e.g. --sleeves TREND")
    ap.add_argument("--warmup", type=int, default=300,
                    help="bars reserved before the first weight (target_weights needs history)")
    ap.add_argument("--intraday", action="store_true")
    ap.add_argument("--universe", default="full", choices=list(TIERS),
                    help="which instruments; a fixed panel starts when its YOUNGEST member does")
    ap.add_argument("--window", type=int, default=2000,
                    help="trailing bars fed to target_weights (verified equivalent before use)")
    ap.add_argument("--no-check", action="store_true", help="skip the window equivalence proof")
    ap.add_argument("--tiers", action="store_true", help="run every universe and compare")
    ap.add_argument("--source", default="mt5", choices=["mt5", "reference"],
                    help="mt5 = broker series (authoritative, short); reference = 20y Yahoo")
    a = ap.parse_args()
    if a.tiers:
        for u in TIERS:
            print("\n" + "#" * 74 + f"\n# UNIVERSE: {u}\n" + "#" * 74)
            try:
                run(a.config, a.sleeves, a.warmup, False, u, a.window, not a.no_check, a.source)
            except SystemExit as e:
                print(f"  skipped: {e}")
    else:
        run(a.config, a.sleeves, a.warmup, a.intraday, a.universe, a.window, not a.no_check, a.source)


if __name__ == "__main__":
    main()
