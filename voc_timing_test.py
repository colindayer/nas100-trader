"""
voc_timing_test.py — Kelly/Malamud/Zhou "Virtue of Complexity" (JF 2024)
applied to daily US100 timing, gauntlet-style.

The paper's recipe, faithfully scaled to our data:
  • G_t: ~14 standardized PRICE-BASED predictors (we lack their macro set —
    dp/dy/ep etc. — so lagged returns, vol, trend distances stand in; the
    MECHANISM under test is RFF + ridgeless P>>T, not the predictor list)
  • Random Fourier Features:  S_t = sqrt(1/P)[sin(g W G_t), cos(g W G_t)],
    W ~ N(0, I), g = 2 (paper's gamma), P = 4096 features from 14 inputs
  • Rolling 252-day training, retrain monthly, RIDGELESS fit via the dual
    (kernel) form — beta = S'(SS' + zI)^{-1} R with z -> 0, so P >> T is cheap
  • Position = clipped scaled forecast, next-day return, 4bp costs on turnover

CONTROLS (what makes this a test, not a demo):
  • shuffled-target: same pipeline trained on PERMUTED returns → must be ~0.
  • momentum baseline: sign(12-1 month return) timer — Nagel's critique says
    VoC mostly re-discovers momentum; if VoC ≈ this baseline, it adds nothing.
  • buy & hold comparison + IS/OOS split + correlation to underlying.

Run on the VPS (needs qqq_hourly_7y.csv from the MT5 bridge):
    python voc_timing_test.py
"""
import sys

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

P_FEATURES = 4096
GAMMA = 2.0
TRAIN_D = 252
RETRAIN = 21
RIDGE_Z = 1e-6
COST = 0.0004
SEED = 7


def daily_closes():
    df = pd.read_csv("qqq_hourly_7y.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    px = df.set_index("timestamp")["close"].resample("1D").last().dropna()
    return px


def build_predictors(px):
    r = px.pct_change()
    G = pd.DataFrame(index=px.index)
    for k in (1, 2, 5, 10, 21, 63, 126, 252):
        G[f"ret{k}"] = px.pct_change(k)
    G["vol21"] = r.rolling(21).std()
    G["vol63"] = r.rolling(63).std()
    G["dma50"] = px / px.rolling(50).mean() - 1
    G["dma200"] = px / px.rolling(200).mean() - 1
    G["skew63"] = r.rolling(63).skew()
    G["acf1"] = r.rolling(63).apply(lambda x: x.autocorr(), raw=False)
    # z-score each predictor on a trailing window (no lookahead)
    Gz = (G - G.rolling(TRAIN_D).mean()) / G.rolling(TRAIN_D).std()
    return Gz.clip(-3, 3)


def rff(Gm, W):
    z = GAMMA * (Gm @ W.T)
    return np.hstack([np.sin(z), np.cos(z)]) / np.sqrt(W.shape[0] * 2)


def run_voc(G, fwd, shuffle=False, seed=SEED):
    rng = np.random.default_rng(seed)
    d = G.shape[1]
    W = rng.normal(size=(P_FEATURES // 2, d))
    idx = G.index
    pos = pd.Series(0.0, index=idx)
    y_all = fwd.values.copy()
    if shuffle:
        y_all = rng.permutation(y_all)
    for t0 in range(TRAIN_D, len(idx) - 1, RETRAIN):
        tr = slice(t0 - TRAIN_D, t0)
        te = slice(t0, min(t0 + RETRAIN, len(idx) - 1))
        Gtr, Gte = G.values[tr], G.values[te]
        ytr = y_all[tr]
        ok = ~np.isnan(Gtr).any(axis=1) & ~np.isnan(ytr)
        if ok.sum() < 60:
            continue
        S = rff(Gtr[ok], W)                      # T x P
        K = S @ S.T + RIDGE_Z * np.eye(ok.sum()) # dual (kernel) ridgeless
        alpha = np.linalg.solve(K, ytr[ok])
        beta = S.T @ alpha                       # P-dim
        # a-priori scaling: unit forecast vol in-train, clipped to +/-1
        f_tr = S @ beta
        scale = np.std(f_tr) or 1.0
        Ste = rff(np.nan_to_num(Gte), W)
        pos.iloc[te] = np.clip((Ste @ beta) / (2 * scale), -1.0, 1.0)
    return pos


def perf(pos, fwd, label):
    ret = pos.shift(0) * fwd - COST * pos.diff().abs().fillna(0)
    ret = ret.dropna()
    if ret.std() == 0:
        print(f"  {label:<26} flat")
        return None
    sh = ret.mean() / ret.std() * np.sqrt(252)
    eq = (1 + ret).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    print(f"  {label:<26} ann={ret.mean()*252:+.1%}  Sharpe={sh:+.2f}  "
          f"maxDD={dd:.1%}")
    return ret


if __name__ == "__main__":
    px = daily_closes()
    G = build_predictors(px)
    fwd = px.pct_change().shift(-1)              # next-day return
    print(f"{len(px)} days ({px.index[0].date()} → {px.index[-1].date()}), "
          f"P={P_FEATURES}, T={TRAIN_D}, gamma={GAMMA}, ridgeless\n")

    split = px.index[TRAIN_D + (len(px) - TRAIN_D) * 6 // 10]
    pos_voc = run_voc(G, fwd)
    pos_shuf = run_voc(G, fwd, shuffle=True)
    mom = np.sign(px.pct_change(252).shift(21)).fillna(0)   # 12-1 momentum timer

    for era, sel in (("IN-SAMPLE", px.index <= split),
                     ("OUT-OF-SAMPLE", px.index > split)):
        print(f"{era} (to/from {split.date()}):")
        r_voc = perf(pos_voc[sel], fwd[sel], "VoC (RFF ridgeless)")
        perf(pos_shuf[sel], fwd[sel], "shuffled-target CONTROL")
        r_mom = perf(mom[sel], fwd[sel], "12-1 momentum baseline")
        perf(pd.Series(1.0, index=px.index)[sel], fwd[sel], "buy & hold")
        if r_voc is not None and r_mom is not None:
            c = r_voc.corr(r_mom.reindex(r_voc.index))
            print(f"  corr(VoC, momentum) = {c:+.2f}  "
                  f"(> 0.6 → it just re-learned momentum — Nagel critique)")
        print()
    print("ADOPTION RULE: VoC must be positive OOS net of costs, beat the")
    print("momentum baseline, decorrelate from it (<0.6), and the shuffled")
    print("control must be ~0 (else pipeline bug). Anything less → FINDINGS.")
