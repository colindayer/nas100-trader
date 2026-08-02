"""READ-ONLY forensics on the connected MT5 account. Places nothing, closes nothing, changes
nothing. Answers one question: where did the money go, and who moved it?

    py scripts\\account_forensics.py                 # last 90 days
    py scripts\\account_forensics.py --days 400      # full account life
    py scripts\\account_forensics.py --export        # also write a CSV of every deal

Written 2026-08-02 because FundedNext demo 34536803 showed day_start_equity 49,338.76 against a
high-water mark of 50,000.00 with trades_today=0, zero open positions, and no ledger entry. An
unexplained 661.24 on an account we believe we control is a bigger problem than any research
result, and this project has ALREADY found two execution surfaces nobody knew were running
(an hourly live_trader.py in Downloads, and a GitHub Actions cron).

The decisive column is MAGIC. Our runner stamps every order with MAGIC. A deal with a different
magic was placed by something else.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

try:
    from scripts.portfolio_mt5 import MAGIC
except Exception:
    MAGIC = 770002


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--export", action="store_true", help="write registry/mt5_history_<acct>.csv")
    a = ap.parse_args()

    if mt5 is None or not mt5.initialize():
        raise SystemExit("MetaTrader5 unavailable — run this on the VPS with the terminal open")

    acct = mt5.account_info()
    if acct is None:
        raise SystemExit("no account info")
    print("=" * 74)
    print(f" ACCOUNT {acct.login} @ {acct.server}   {'DEMO' if acct.trade_mode == 0 else 'REAL'}")
    print("=" * 74)
    print(f"  balance {acct.balance:,.2f}   equity {acct.equity:,.2f}   "
          f"profit {acct.profit:,.2f}")
    print(f"  margin  {acct.margin:,.2f}    free {acct.margin_free:,.2f}")

    # ---- open positions, ours and foreign
    pos = mt5.positions_get()
    if pos is None:
        print("\n  !! positions_get() FAILED — cannot confirm the account is flat")
    else:
        ours = [p for p in pos if p.magic == MAGIC]
        foreign = [p for p in pos if p.magic != MAGIC]
        print(f"\n  open positions: {len(pos)}  ({len(ours)} ours, {len(foreign)} FOREIGN)")
        for p in foreign:
            print(f"    !! FOREIGN {p.symbol} vol={p.volume} magic={p.magic} "
                  f"profit={p.profit:.2f} comment={p.comment!r}")

    # ---- every deal in the window
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    deals = mt5.history_deals_get(since, datetime.now(timezone.utc) + timedelta(days=1))
    if deals is None:
        print("\n  !! history_deals_get() FAILED — cannot audit history")
        return
    print(f"\n  {len(deals)} deals in the last {a.days} days")

    by_magic = defaultdict(lambda: {"n": 0, "profit": 0.0, "symbols": Counter(),
                                    "comments": Counter()})
    total = 0.0
    for d in deals:
        k = by_magic[d.magic]
        k["n"] += 1
        pl = d.profit + getattr(d, "commission", 0.0) + getattr(d, "swap", 0.0) + \
            getattr(d, "fee", 0.0)
        k["profit"] += pl
        total += pl
        k["symbols"][d.symbol] += 1
        if d.comment:
            k["comments"][d.comment] += 1

    print(f"\n  {'magic':>12}  {'deals':>6}  {'net P/L':>12}   who")
    for magic, v in sorted(by_magic.items(), key=lambda x: x[1]["profit"]):
        who = "OURS (portfolio runner)" if magic == MAGIC else (
            "manual / terminal" if magic == 0 else "!! UNKNOWN AUTOMATION")
        print(f"  {magic:>12}  {v['n']:>6}  {v['profit']:>12,.2f}   {who}")
        if v["symbols"]:
            print(f"               symbols: {dict(v['symbols'].most_common(6))}")
        if v["comments"]:
            print(f"               comments: {dict(v['comments'].most_common(4))}")
    print(f"\n  TOTAL net across all sources: {total:,.2f}")

    # ---- balance operations (deposits/withdrawals/credits) explain equity moves with no trade
    bal = [d for d in deals if d.type == getattr(mt5, "DEAL_TYPE_BALANCE", 2)]
    if bal:
        print(f"\n  {len(bal)} BALANCE operations (not trades):")
        for d in bal:
            print(f"    {datetime.fromtimestamp(d.time, timezone.utc):%Y-%m-%d %H:%M} "
                  f"{d.profit:>12,.2f}  {d.comment!r}")

    print("\n  READ THIS: any row above with a magic that is neither ours nor 0 was placed by "
          "automation we have not accounted for. Investigate before enabling anything.")

    if a.export:
        out = Path(__file__).resolve().parents[1] / "registry" / f"mt5_history_{acct.login}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time_utc", "ticket", "order", "symbol", "type", "entry", "volume",
                        "price", "profit", "commission", "swap", "fee", "magic", "comment"])
            for d in deals:
                w.writerow([datetime.fromtimestamp(d.time, timezone.utc).isoformat(),
                            d.ticket, d.order, d.symbol, d.type, d.entry, d.volume, d.price,
                            d.profit, getattr(d, "commission", 0.0), getattr(d, "swap", 0.0),
                            getattr(d, "fee", 0.0), d.magic, d.comment])
        print(f"\n  exported {len(deals)} deals -> {out}")
        print("  This is the MT5 history export that has been outstanding. Keep it.")


if __name__ == "__main__":
    main()
