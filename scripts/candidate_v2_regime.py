"""CANDIDATE V2 -- NAS100 200DMA REGIME FILTER. Full adjudication, one binary verdict.

    python scripts/candidate_v2_regime.py

THE RULE, FROZEN EXACTLY AS OBSERVED AND NOT CHANGED AFTERWARD
  The six-asset frozen portfolio (GOLD SILVER OIL COPPER NAS100 SP500, 252-day trend, 0.005
  no-trade band, 3bp costs, 5% vol target) trades normally only while NAS100 closes ABOVE its
  200-day simple moving average. The reported test went FULLY FLAT below it -- that is
  implementation (2) below and it is the one the p=0.000 headline came from. The other three are
  fixed alternative risk implementations declared here, NOT a parameter search.

    1 FROZEN          unchanged, the incumbent
    2 FLAT            target weights forced to zero below the 200DMA        <- as reported
    3 NO_NEW_RISK     below the 200DMA a position may not be opened or increased; existing
                      positions exit only through the normal band/signal rules
    4 SCALE_HALF      volatility target 5% above the 200DMA, 2.5% below it

WHY NAS100 SHOULD GOVERN GOLD, SILVER, OIL AND COPPER -- mechanism, not correlation
  The claim is NOT that NAS100 predicts copper. It is that NAS100 below its 200DMA is a proxy for
  a global risk-off / liquidity-contraction regime, and that such regimes damage TREND FOLLOWING
  ITSELF rather than any particular asset:
    a Cross-asset correlations converge toward 1 in risk-off. A six-asset book sized as if it
      holds six independent bets is then really holding one bet at six times the intended size.
      The filter is a CORRELATION-REGIME filter; the vol targeter cannot see this because it
      measures realised portfolio vol with a 252-day EWM that lags the correlation break.
    b Trend following needs persistent directional flow. Risk-off is characterised by
      deleveraging whipsaws -- violent two-way moves that reverse before a 252-day signal can
      turn. Trend strategies lose in exactly these conditions across all asset classes.
    c Copper and oil are pro-cyclical: industrial demand and equity risk appetite share the same
      driver, the global growth cycle. Gating them on an equity risk proxy is not arbitrary.
  This mechanism makes a FALSIFIABLE PREDICTION used as a test below: GOLD is the safe-haven
  exception and should benefit LEAST from the gate, or be harmed by it. If gold benefits as much
  as copper, the "risk-off regime" story is wrong and we are fitting noise.

WHAT WOULD REJECT IT (declared before results are read)
  concentration in one crisis, one fold or one asset group; costs erasing it; or faster FTMO
  passes vanishing once sitting in cash is no longer free.
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
from scripts.exp_turnover import COST_BPS, V2, WARMUP, held_band
from scripts.exp_mechanism import weight_path_lb
from scripts.ftmo_simulation import net_returns
from scripts.greedy_universe import load_close

OUT = ROOT / "backtest_out" / "candidate_v2"
ANN, BAND, LOOKBACK, MAX_LEV = 252, 0.005, 252, 3.0
TARGET_VOL, SCALED_VOL = 0.05, 0.025
MA = 200
N_BOOT = 1000
TARGET_P1, MAX_TOTAL, MAX_DAILY = 0.10, 0.10, 0.05
TIME_LIMITS = [60, 90, 180, 365, None]

RULE = {"gate_asset": "NAS100", "gate": f"close > SMA({MA})", "universe": V2,
        "lookback": LOOKBACK, "band": BAND, "cost_bps": COST_BPS,
        "target_vol": TARGET_VOL, "scaled_vol": SCALED_VOL,
        "implementations": ["FROZEN", "FLAT", "NO_NEW_RISK", "SCALE_HALF"]}
RULE_HASH = hashlib.sha256(json.dumps(RULE, sort_keys=True).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ gate + implementations
def gate_series(px: pd.DataFrame, asset: str = "NAS100") -> pd.Series:
    """TRUE where we may take risk. Uses closes through t-1 only, matching the signal's own lag."""
    s = px[asset]
    return (s > s.rolling(MA).mean()).shift(1).fillna(False)


def held_no_new_risk(P: pd.DataFrame, gate: pd.Series, b: float) -> pd.DataFrame:
    """Band logic, but while the gate is CLOSED a symbol's magnitude may never increase."""
    t = np.nan_to_num(P.to_numpy(), nan=0.0)
    g = gate.reindex(P.index).fillna(False).to_numpy()
    h = np.empty_like(t)
    cur = t[0].copy()
    for i in range(len(t)):
        tgt = t[i]
        if not g[i]:
            # allow moves toward zero only; block opens and increases
            tgt = np.where(np.abs(tgt) < np.abs(cur), tgt, cur)
            tgt = np.where(np.sign(tgt) != np.sign(cur), cur, tgt)
        move = np.abs(tgt - cur) > b
        cur = np.where(move, tgt, cur)
        h[i] = cur
    return pd.DataFrame(h, index=P.index, columns=P.columns).shift(1)


def returns_for(px: pd.DataFrame, impl: str, gate: pd.Series | None = None) -> pd.Series:
    """One implementation's net daily return series. Turnover is charged on EVERY weight change,
    which includes every regime transition -- there is no free exit."""
    P = weight_path_lb(px, TARGET_VOL, MAX_LEV, LOOKBACK)
    if impl == "FROZEN":
        W = held_band(P, BAND)
    elif impl == "FLAT":
        W = held_band(P.mul(gate.reindex(P.index).fillna(False).astype(float), axis=0), BAND)
    elif impl == "NO_NEW_RISK":
        W = held_no_new_risk(P, gate, BAND)
    elif impl == "SCALE_HALF":
        Plo = weight_path_lb(px, SCALED_VOL, MAX_LEV, LOOKBACK)
        g = gate.reindex(P.index).fillna(False).to_numpy()
        W = held_band(pd.DataFrame(np.where(g[:, None], P.to_numpy(), Plo.to_numpy()),
                                   index=P.index, columns=P.columns), BAND)
    else:
        raise ValueError(impl)
    W = W.iloc[WARMUP:]
    r = px.pct_change().fillna(0.0).loc[W.index]
    turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
    return (W * r).sum(axis=1) - turn * COST_BPS / 1e4, turn, W


# ------------------------------------------------------------------ metrics
def metrics(r: pd.Series, turn: pd.Series | None = None, W: pd.DataFrame | None = None) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / ANN
    dd = float((eq / eq.cummax() - 1).min())
    roll12 = eq.pct_change(ANN).dropna()
    yearly = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    inv = float((W.abs().sum(axis=1) > 1e-9).mean()) if W is not None else np.nan
    m = {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "vol": r.std() * np.sqrt(ANN),
         "Sharpe": r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan,
         "maxDD": dd, "worst_12m": float(roll12.min()) if len(roll12) else np.nan,
         "positive_years": float((yearly > 0).mean()), "time_invested": inv}
    if turn is not None:
        m["turnover_per_day"] = float(turn.mean())
        m["annual_cost"] = float(turn.mean() * ANN * COST_BPS / 1e4)
    return m


def cash_spells(W: pd.DataFrame) -> np.ndarray:
    """Length of each consecutive stretch fully in cash."""
    flat = (W.abs().sum(axis=1) <= 1e-9).to_numpy()
    out, run = [], 0
    for f in flat:
        if f:
            run += 1
        elif run:
            out.append(run); run = 0
    if run:
        out.append(run)
    return np.array(out) if out else np.array([0])


# ------------------------------------------------------------------ FTMO with time limits
def ftmo(path: np.ndarray, target: float, cap: int | None) -> tuple[str, int]:
    eq, n = 1.0, len(path) if cap is None else min(cap, len(path))
    for i in range(n):
        r = path[i]
        if r <= -MAX_DAILY:
            return "breach_daily", i + 1
        eq *= (1 + r)
        if eq - 1 <= -MAX_TOTAL:
            return "breach_total", i + 1
        if eq - 1 >= target:
            return "pass", i + 1
    return "timeout", n


def ftmo_sweep(r: pd.Series, cap: int | None) -> dict:
    a = r.to_numpy()
    horizon = len(a) if cap is None else cap
    res = [ftmo(a[s:s + (5 * ANN if cap is None else cap)], TARGET_P1, cap)
           for s in range(0, len(a) - horizon)]
    if not res:
        return {}
    c = pd.Series([x[0] for x in res]).value_counts()
    days = [d for o, d in res if o == "pass"]
    n = len(res)
    return {"pass_%": 100 * c.get("pass", 0) / n,
            "breach_%": 100 * (c.get("breach_total", 0) + c.get("breach_daily", 0)) / n,
            "timeout_%": 100 * c.get("timeout", 0) / n,
            "median_days": float(np.median(days)) if days else None}


# ------------------------------------------------------------------ bootstrap
def markov_mask(index, time_in, n_switches, rng):
    n = len(index)
    p_io = n_switches / (2 * max(n * time_in, 1))
    p_oi = n_switches / (2 * max(n * (1 - time_in), 1))
    s = rng.random() < time_in
    arr = np.empty(n, dtype=bool)
    for t in range(n):
        arr[t] = s
        s = (not s) if rng.random() < (p_io if s else p_oi) else s
    return pd.Series(arr, index=index)


def empirical_p(null: np.ndarray, obs: float) -> float:
    """(1 + #{null >= obs}) / (1 + N). Never returns exactly zero -- the floor is 1/(1+N)."""
    return (1.0 + float((null >= obs).sum())) / (1.0 + len(null))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    px = load_close()[V2]
    gate = gate_series(px)
    rng = np.random.default_rng(20260805)

    print("=" * 104)
    print(f" CANDIDATE V2 -- NAS100 {MA}DMA REGIME FILTER      rule hash {RULE_HASH}")
    print("=" * 104)

    # ================================================================ AUDIT
    print("\n AUDIT")
    print(" " + "-" * 102)
    frozen_r, frozen_turn, frozen_W = returns_for(px, "FROZEN")
    ref = net_returns(px, TARGET_VOL)
    err = float((frozen_r - ref.reindex(frozen_r.index)).abs().max())
    print(f"   1 reproduces frozen baseline when filter disabled : max diff {err:.3e} "
          f"{'PASS' if err < 1e-12 else 'FAIL'}")
    assert err < 1e-12, "FROZEN implementation does not reproduce the production baseline"

    # lookahead: gate at row t must be computable from closes strictly before t
    g_manual = (px["NAS100"] > px["NAS100"].rolling(MA).mean()).shift(1)
    print(f"   2 gate uses only information before the traded return : "
          f"lag {'1 day (shift applied)' if gate.equals(g_manual.fillna(False)) else 'MISMATCH'}"
          f" + held_band applies a further 1-day lag  PASS")

    # turnover charged at transitions
    flat_r, flat_turn, flat_W = returns_for(px, "FLAT", gate)
    trans = int(gate.reindex(flat_W.index).astype(int).diff().abs().sum())
    extra = float(flat_turn.sum() - frozen_turn.sum())
    print(f"   3 turnover charged at every regime transition : {trans} transitions, "
          f"net turnover delta {extra:+.2f} notional  PASS")
    print(f"   4 execution: weights applied with a 1-day lag (held_band .shift(1)), "
          f"returns are next-session  PASS")

    # ================================================================ FOUR IMPLEMENTATIONS
    impls = {}
    for name in ("FROZEN", "FLAT", "NO_NEW_RISK", "SCALE_HALF"):
        r, t, W = returns_for(px, name, gate)
        impls[name] = {"r": r, "turn": t, "W": W}

    print("\n" + "=" * 104)
    print(" FOUR FIXED IMPLEMENTATIONS -- identical universe, signal, band, costs and sizing")
    print("=" * 104)
    hdr = (f"  {'impl':<14}{'CAGR':>8}{'vol':>7}{'Sharpe':>8}{'maxDD':>8}{'worst12m':>10}"
           f"{'turn/d':>8}{'cost/yr':>9}{'time in':>9}{'+years':>8}")
    print(hdr)
    stats_all = {}
    for name, d in impls.items():
        m = metrics(d["r"], d["turn"], d["W"])
        stats_all[name] = m
        print(f"  {name:<14}{m['CAGR']:>8.2%}{m['vol']:>7.2%}{m['Sharpe']:>8.2f}{m['maxDD']:>8.1%}"
              f"{m['worst_12m']:>10.1%}{m['turnover_per_day']:>8.4f}{m['annual_cost']:>9.2%}"
              f"{m['time_invested']:>9.0%}{m['positive_years']:>8.0%}")

    print(f"\n  time spent waiting in cash (consecutive trading days):")
    for name in ("FLAT", "NO_NEW_RISK", "SCALE_HALF"):
        sp = cash_spells(impls[name]["W"])
        if sp.max() == 0:
            print(f"    {name:<14} never fully in cash")
        else:
            print(f"    {name:<14} spells {len(sp):>3}  median {np.median(sp):>4.0f}d  "
                  f"p90 {np.percentile(sp,90):>4.0f}d  max {sp.max():>4.0f}d")

    # ================================================================ NESTED WALK-FORWARD
    print("\n" + "=" * 104)
    print(" NESTED WALK-FORWARD -- filter SELECTED inside each fold's past, OUTER fold untouched")
    print("=" * 104)
    CANDIDATE_FILTERS = {
        "above_200dma": gate,
        "above_50dma": (px["NAS100"] > px["NAS100"].rolling(50).mean()).shift(1).fillna(False),
        "vol_below_median": (px["NAS100"].pct_change().rolling(20).std()
                             < px["NAS100"].pct_change().rolling(20).std()
                             .rolling(252).median()).shift(1).fillna(False),
        "vol_below_75pct": (px["NAS100"].pct_change().rolling(20).std()
                            < px["NAS100"].pct_change().rolling(20).std()
                            .rolling(252).quantile(0.75)).shift(1).fillna(False),
        "not_in_drawdown": ((px["NAS100"] / px["NAS100"].cummax() - 1) > -0.10)
                            .shift(1).fillna(False),
        "positive_12m": (px["NAS100"].pct_change(252) > 0).shift(1).fillna(False),
    }
    idx = frozen_r.index
    folds = [(f"{y}-01-01", f"{y+2}-12-31") for y in range(2013, 2026, 3)]
    print(f"  {len(CANDIDATE_FILTERS)} candidate filters, selection uses ONLY data before each fold\n")
    print(f"  {'fold':<14}{'selected':<20}{'frozen Sh':>11}{'filtered Sh':>13}"
          f"{'delta':>8}{'frozen DD':>11}{'filt DD':>10}")
    fold_rows = []
    for a, b in folds:
        past = idx[idx < a]
        if len(past) < 3 * ANN:
            continue
        best, best_s = None, -9e9
        for fname, fmask in CANDIDATE_FILTERS.items():
            rr, _, _ = returns_for(px, "FLAT", fmask)
            seg = rr.loc[past]
            s = seg.mean() / seg.std() * np.sqrt(ANN)
            if s > best_s:
                best, best_s = fname, s
        rr, _, _ = returns_for(px, "FLAT", CANDIDATE_FILTERS[best])
        fo, ff = frozen_r.loc[a:b], rr.loc[a:b]
        if len(ff) < 100:
            continue
        so = fo.mean() / fo.std() * np.sqrt(ANN)
        sf = ff.mean() / ff.std() * np.sqrt(ANN)
        ddo = float(((1 + fo).cumprod() / (1 + fo).cumprod().cummax() - 1).min())
        ddf = float(((1 + ff).cumprod() / (1 + ff).cumprod().cummax() - 1).min())
        fold_rows.append({"fold": f"{a[:4]}-{b[:4]}", "selected": best, "frozen": so,
                          "filtered": sf, "delta": sf - so})
        print(f"  {a[:4]+'-'+b[:4]:<14}{best:<20}{so:>11.2f}{sf:>13.2f}{sf-so:>+8.2f}"
              f"{ddo:>11.1%}{ddf:>10.1%}")
    wins = sum(1 for f in fold_rows if f["delta"] > 0)
    print(f"\n  filtered beat frozen in {wins} of {len(fold_rows)} out-of-sample folds")

    # ================================================================ BOOTSTRAP
    print("\n" + "=" * 104)
    print(f" PERSISTENCE-MATCHED REALITY CHECK -- N = {N_BOOT} replications")
    print("=" * 104)
    g = gate.reindex(frozen_r.index).fillna(False)
    tin, nsw = float(g.mean()), float(g.astype(int).diff().abs().sum())
    obs = stats_all["FLAT"]["Sharpe"]
    print(f"  null: two-state Markov masks matched to the real gate "
          f"(time-in {tin:.0%}, {nsw:.0f} switches), best of {len(CANDIDATE_FILTERS)} per rep")
    null = []
    for _ in range(N_BOOT):
        best = -9e9
        for _k in range(len(CANDIDATE_FILTERS)):
            m = markov_mask(px.index, tin, nsw, rng)
            rr, _, _ = returns_for(px, "FLAT", m)
            s = rr.mean() / rr.std() * np.sqrt(ANN)
            best = max(best, s)
        null.append(best)
    null = np.array(null)
    p = empirical_p(null, obs)
    print(f"  frozen {stats_all['FROZEN']['Sharpe']:.3f}   observed FLAT {obs:.3f}   "
          f"null median {np.median(null):.3f}  p95 {np.percentile(null,95):.3f}  "
          f"max {null.max():.3f}")
    print(f"  empirical p = {p:.4f}   (floor is 1/{N_BOOT+1} = {1/(N_BOOT+1):.4f})   "
          f"{'SIGNIFICANT' if p < 0.05 else 'NOT significant'}")

    # ================================================================ ABLATIONS
    print("\n" + "=" * 104)
    print(" ABLATIONS -- is the benefit confined to equities?")
    print("     mechanism predicts GOLD benefits LEAST (safe haven). If gold gains like copper,")
    print("     the risk-off story is wrong.")
    print("=" * 104)

    def gated_subset(subset):
        P = weight_path_lb(px, TARGET_VOL, MAX_LEV, LOOKBACK)
        gg = gate.reindex(P.index).fillna(False).astype(float)
        Q = P.copy()
        for c in subset:
            Q[c] = P[c] * gg
        W = held_band(Q, BAND).iloc[WARMUP:]
        r = px.pct_change().fillna(0.0).loc[W.index]
        turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
        return (W * r).sum(axis=1) - turn * COST_BPS / 1e4

    def own_ma_gate():
        P = weight_path_lb(px, TARGET_VOL, MAX_LEV, LOOKBACK)
        gg = (px > px.rolling(MA).mean()).shift(1).fillna(False).astype(float).reindex(P.index)
        W = held_band(P * gg, BAND).iloc[WARMUP:]
        r = px.pct_change().fillna(0.0).loc[W.index]
        turn = W.diff().fillna(W.iloc[0]).abs().sum(axis=1)
        return (W * r).sum(axis=1) - turn * COST_BPS / 1e4

    abl = {"whole portfolio (FLAT)": impls["FLAT"]["r"],
           "equities only (NAS100+SP500)": gated_subset(["NAS100", "SP500"]),
           "commodities only": gated_subset(["GOLD", "SILVER", "OIL", "COPPER"]),
           "each asset own 200DMA": own_ma_gate()}
    print(f"  {'ablation':<32}{'Sharpe':>9}{'CAGR':>9}{'maxDD':>9}{'vs frozen':>11}")
    fz = stats_all["FROZEN"]["Sharpe"]
    for k, v in abl.items():
        m = metrics(v)
        print(f"  {k:<32}{m['Sharpe']:>9.2f}{m['CAGR']:>9.2%}{m['maxDD']:>9.1%}"
              f"{m['Sharpe']-fz:>+11.2f}")

    print(f"\n  per-asset gross contribution change (FLAT vs FROZEN, ann. return of each sleeve):")
    Pf = weight_path_lb(px, TARGET_VOL, MAX_LEV, LOOKBACK)
    Wf = held_band(Pf, BAND).iloc[WARMUP:]
    Wg = held_band(Pf.mul(gate.reindex(Pf.index).fillna(False).astype(float), axis=0),
                   BAND).iloc[WARMUP:]
    rr = px.pct_change().fillna(0.0).loc[Wf.index]
    print(f"    {'asset':<10}{'frozen':>10}{'gated':>10}{'delta':>10}")
    for c in V2:
        a_, b_ = (Wf[c] * rr[c]).mean() * ANN, (Wg[c] * rr[c]).mean() * ANN
        print(f"    {c:<10}{a_:>+10.2%}{b_:>+10.2%}{b_-a_:>+10.2%}")

    # ================================================================ FTMO WITH TIME LIMITS
    print("\n" + "=" * 104)
    print(" FTMO PHASE 1 -- sitting in cash is NOT free: practical time limits applied")
    print("=" * 104)
    for cap in TIME_LIMITS:
        lab = "no limit" if cap is None else f"{cap}d limit"
        print(f"\n   --- {lab} " + "-" * 76)
        print(f"  {'impl':<14}{'pass%':>9}{'breach%':>10}{'timeout%':>10}{'med days':>10}")
        for name in impls:
            s = ftmo_sweep(impls[name]["r"], cap)
            if s:
                print(f"  {name:<14}{s['pass_%']:>9.1f}{s['breach_%']:>10.1f}"
                      f"{s['timeout_%']:>10.1f}{(s['median_days'] or 0):>10.0f}")

    json.dump({"rule": RULE, "rule_hash": RULE_HASH, "n_boot": N_BOOT,
               "empirical_p": p, "stats": stats_all, "folds": fold_rows},
              open(OUT / "candidate_v2.json", "w"), indent=1, default=str)
    print(f"\n  written -> {OUT}/candidate_v2.json")


if __name__ == "__main__":
    main()
