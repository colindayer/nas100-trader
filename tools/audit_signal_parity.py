"""
audit_signal_parity.py -- did the LIVE runs decide what the research says they
should have? Day-by-day, per strategy: expected signals (recomputed from data,
exact backtest definitions) vs what the live logs actually show (signals,
evaluations, gate-skips). Read-only; run on each host that owns logs (Mac +VPS).

Usage:  python tools/audit_signal_parity.py [--days 10]
Verdict per day: OK (live matches expectation), MISS (setup existed, live ran,
no signal logged -> investigate), DOWN (live never evaluated that day).
"""
import argparse
import glob
import os
import re
from collections import defaultdict

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def expected_signals(days_back):
    """Recompute S1/S5 expected signal counts per day (exact backtest features).
    ponytail: S1+S5 only -- S5 is the daily canary, S1 the sparse one; S2/S3/S4
    can be added when these two prove the harness."""
    import pytz, warnings
    warnings.filterwarnings("ignore")
    eastern = pytz.timezone("US/Eastern")
    df = pd.read_csv(os.path.join(REPO, "qqq_hourly_7y.csv"))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    q = df[df["symbol"] == "QQQ"].set_index("timestamp").tz_convert(eastern)[
        ["open", "high", "low", "close", "volume"]]
    q.columns = ["Open", "High", "Low", "Close", "Volume"]
    try:  # splice fresh extended-hours bars so "today" is covered
        import sys; sys.path.insert(0, REPO)
        from alpaca_broker import AlpacaBroker
        fresh = AlpacaBroker().get_bars("QQQ", "1Hour", 1200)
        q = pd.concat([q, fresh[fresh.index > q.index.max()]])
    except Exception as e:
        print(f"(no fresh splice: {e} -- expected counts end {q.index.max().date()})")
    q["Date"] = q.index.date
    q["SD"] = q.index.map(lambda i: (i + pd.Timedelta(days=1)).date()
                          if i.hour >= 18 else i.date())
    ab = q[q.index.map(lambda i: i.hour >= 18 or i.hour < 2)]
    q["AL"] = q["SD"].map(ab.groupby("SD")["Low"].min())
    q["InS"] = q.index.map(lambda x: (2 <= x.hour < 5) or (9 <= x.hour < 12))
    tp = (q["High"] + q["Low"] + q["Close"]) / 3
    vv, ct, cv, p_ = [], 0.0, 0.0, None
    for i in range(len(q)):
        d = q["Date"].iloc[i]
        if d != p_: ct = cv = 0.0; p_ = d
        v = q["Volume"].iloc[i]
        if v > 0: ct += tp.iloc[i] * v; cv += v
        vv.append(ct / cv if cv > 0 else float("nan"))
    q["VWAP"] = vv
    dc = q[q.index.hour == 16][["Close"]].copy(); dc.index = dc.index.date
    dc = dc[~dc.index.duplicated(keep="last")]
    q["EMA50"] = q["Date"].map(dc["Close"].ewm(span=50).mean().to_dict())
    pc = q["Close"].shift(1)
    tr = pd.concat([q["High"] - q["Low"], (q["High"] - pc).abs(),
                    (q["Low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean(); q["HV"] = atr > 1.5 * atr.rolling(200).mean()
    s1 = ((q["Low"] < q["AL"]) & (q["Close"] > q["AL"]) & q["InS"]
          & (q["Close"] > q["VWAP"]) & (q["Close"] > q["EMA50"])
          & ~q["HV"] & q["AL"].notna())
    orb = q[q.index.hour == 9]
    q["OH"] = q["Date"].map({d: h for d, h in zip(orb["Date"], orb["High"])})
    q["OV"] = q["Date"].map({d: v for d, v in zip(orb["Date"], orb["Volume"])})
    s5 = (q.index.map(lambda x: 10 <= x.hour <= 13) & (q["Close"] > q["OH"])
          & q["OH"].notna() & (q["Volume"] > q["OV"] * 0.6))
    per = pd.DataFrame({"S1_exp": s1, "S5_exp": s5}).groupby(q["Date"]).sum()
    return per.tail(days_back)


def live_log_by_day():
    """Per day: strategy evaluations, signals, and gate reasons from logs/."""
    days = defaultdict(lambda: defaultdict(int))
    date_rx = re.compile(r"^(\d{4}-\d{2}-\d{2})")
    pats = {
        "S1_eval": re.compile(r"S1 (no signal|SIGNAL|skip|pause)"),
        "S1_sig": re.compile(r"S1 SIGNAL"),
        "S1_gexblock": re.compile(r"S1 skip: GEX positive"),
        "S5_eval": re.compile(r"S5[: ].*(no|SIGNAL|not formed|breakout|pause|skip)", re.I),
        "S5_sig": re.compile(r"S5 SIGNAL"),
        "live_run": re.compile(r"START session=.*dry_run=False"),
        "dry_run": re.compile(r"START session=.*dry_run=True"),
    }
    for p in glob.glob(os.path.join(REPO, "logs", "*.log")):
        for ln in open(p, encoding="utf-8", errors="replace"):
            m = date_rx.match(ln)
            if not m:
                continue
            d = m.group(1)
            for k, rx in pats.items():
                if rx.search(ln):
                    days[d][k] += 1
    return days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    args = ap.parse_args()

    exp = expected_signals(args.days)
    live = live_log_by_day()

    print(f"\n{'date':12} {'S1 exp':>6} {'S1 live':>7} {'S5 exp':>6} {'S5 live':>7} "
          f"{'runs(l/d)':>9}  verdict")
    for d, row in exp.iterrows():
        ds = str(d)
        lv = live.get(ds, {})
        runs = f"{lv.get('live_run', 0)}/{lv.get('dry_run', 0)}"
        s1e, s5e = int(row["S1_exp"]), int(row["S5_exp"])
        s1l, s5l = lv.get("S1_sig", 0), lv.get("S5_sig", 0)
        evaluated = (lv.get("S1_eval", 0) + lv.get("S5_eval", 0)) > 0
        if not evaluated:
            v = "DOWN (no evaluations in this host's logs)"
        elif s5e > 0 and s5l == 0 and lv.get("S5_eval", 0) > 0:
            v = "MISS? setup existed, live evaluated, no S5 signal -> check gates/timing"
        elif s1e > 0 and s1l == 0 and lv.get("S1_gexblock", 0) > 0:
            v = "OK (S1 blocked by GEX gate -- by design)"
        else:
            v = "OK"
        print(f"{ds:12} {s1e:6} {s1l:7} {s5e:6} {s5l:7} {runs:>9}  {v}")
    print("\nNote: 'live' counts come from THIS host's logs only. Run on the VPS "
          "for MT5 truth. Expected counts are bar-level (live caps ~1 trade/day).")


if __name__ == "__main__":
    main()
