"""Build BrokerProfile from a raw capture and emit the capability report. NO MT5 REQUIRED.

    py scripts/broker_report.py                       # newest capture
    py scripts/broker_report.py --compare             # every capture side by side
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from broker.profile import BrokerProfile

UNI = ROOT / "data" / "universe"


def load(csv_path: Path) -> BrokerProfile:
    tag = csv_path.stem.replace("BROKER_RAW_", "")
    meta = UNI / f"BROKER_META_{tag}.json"
    return BrokerProfile.from_csv(csv_path, meta if meta.exists() else None)


def show(p: BrokerProfile, equity: float):
    rep = p.capability_report()
    print("=" * 96)
    print(f" {rep['broker']}  |  {rep['server']}  |  login {rep['login']}  "
          f"|  captured {rep['captured_utc']}")
    print("=" * 96)
    print(f"  symbols {rep['n_symbols']}   tradable {rep['n_tradable']}   "
          f"trend-suitable {rep['trend_universe_size']}")
    print(f"\n  ASSET CLASSES")
    for k, v in rep["asset_classes"].items():
        n_tr = len([s for s in p.by_class(k) if s.tradable])
        n_hist = len([s for s in p.by_class(k) if s.trend_suitable])
        print(f"    {k:<16}{v:>5} symbols  {n_tr:>4} tradable  {n_hist:>4} with >=1000 D1")
    if rep["missing_asset_classes"]:
        print(f"\n  MISSING: {', '.join(rep['missing_asset_classes'])}")
    h = rep["history"]
    print(f"\n  HISTORY   success {h['success_rate']:.0%}   "
          f"median {h['median_d1_bars']:.0f} D1 bars   earliest {h['earliest_d1'] or 'n/a'}")
    if h["median_latency_s"] is not None:
        print(f"            median latency to first bar {h['median_latency_s']:.2f}s")
    print(f"\n  MODES  trade {rep['trade_modes']}")
    print(f"         exec  {rep['execution_modes']}")
    print(f"         swap  {rep['swap_modes']}")
    print(f"\n  LIMITATIONS")
    for l in rep["limitations"]:
        print(f"    - {l}")

    fin = p.financing_table(equity)
    rel = fin[fin.reliable]
    if len(rel):
        print(f"\n  FINANCING (per 1.0 lot, ${equity:,.0f} equity) — 10 costliest longs")
        w = rel.sort_values("long_usd_night").head(10)
        print(f"    {'symbol':<14}{'class':<15}{'$/night':>10}{'20d':>9}{'60d':>9}{'120d':>9}")
        for _, r in w.iterrows():
            print(f"    {r.symbol:<14}{r.asset_class:<15}{r.long_usd_night:>10.2f}"
                  f"{r.long_drag_20d:>9.2%}{r.long_drag_60d:>9.2%}{r.long_drag_120d:>9.2%}")
    out = p.save(UNI)
    print(f"\n  written -> {out}/BROKER_CAPABILITY.json, BROKER_SYMBOLS.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, default=100000.0)
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    caps = sorted(glob.glob(str(UNI / "BROKER_RAW_*.csv")))
    caps = [c for c in caps if len(Path(c).stem.split("_")) <= 3]  # skip timestamped copies
    if not caps:
        sys.exit(f"no captures in {UNI} — run scripts/broker_probe.py on the VPS first")
    if a.compare and len(caps) > 1:
        rows = []
        for c in caps:
            p = load(Path(c)); r = p.capability_report()
            rows.append({"broker": r["broker"], "server": r["server"],
                         "symbols": r["n_symbols"], "tradable": r["n_tradable"],
                         "trend_suitable": r["trend_universe_size"],
                         "missing": ",".join(r["missing_asset_classes"]),
                         **{f"n_{k}": v for k, v in r["asset_classes"].items()}})
        print(pd.DataFrame(rows).to_string(index=False))
        return
    for c in caps:
        show(load(Path(c)), a.equity)


if __name__ == "__main__":
    main()
