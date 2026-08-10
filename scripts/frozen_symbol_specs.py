"""PHASE 1 — exact broker specs for the frozen legs. No assumptions, no conventions.

    py scripts\\frozen_symbol_specs.py

Captures EVERY field MT5 exposes for the seven production-relevant symbols, plus the
d1_from/d1_to dates that BrokerProfile V1 is missing. Also pulls any completed deals with
NONZERO swap, which is the only way to VERIFY the swap conversion rather than assert it.

Read-only. No trading calls. copy_rates is limited to 7 symbols already warm in Market Watch,
so it costs seconds and no meaningful disk.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 required")
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe"
SYMS = ["XAUUSD", "XAGUSD", "USOIL.cash", "UKOIL.cash", "XCUUSD", "US100.cash", "US500.cash"]

SM = {0: "DISABLED", 1: "POINTS", 2: "SYMBOL_CURRENCY", 3: "MARGIN_CURRENCY",
      4: "DEPOSIT_CURRENCY", 5: "INT_CURRENT", 6: "INT_OPEN", 7: "REOPEN_CURRENT",
      8: "REOPEN_BID"}
CM = {0: "FOREX", 1: "FUTURES", 2: "CFD", 3: "CFDINDEX", 4: "CFDLEVERAGE",
      5: "FOREX_NO_LEV", 32: "EXCH_STOCKS", 33: "EXCH_FUTURES", 35: "EXCH_BONDS"}


def main():
    if not mt5.initialize():
        sys.exit(f"initialize failed: {mt5.last_error()}")
    a = mt5.account_info()
    if a is None:
        mt5.shutdown(); sys.exit("HALT: not logged in")
    lg = sv = None
    for line in (ROOT / "config" / "guardian.env").read_text().splitlines():
        s = line.strip()
        if s.startswith("ACCOUNT_LOGIN"):
            lg = int(s.split("=", 1)[1].strip())
        elif s.startswith("ACCOUNT_SERVER_CONTAINS"):
            sv = s.split("=", 1)[1].strip().upper()
    if int(a.login) != lg or sv not in str(a.server).upper():
        mt5.shutdown()
        sys.exit(f"HALT: bound to {lg}/~{sv}, connected to {a.login}/{a.server}")
    print(f"IDENTITY OK -> {a.login} {a.server}\n")

    rows = []
    for name in SYMS:
        if not mt5.symbol_select(name, True):
            print(f"  {name}: SELECT FAILED"); continue
        i = mt5.symbol_info(name)
        if i is None:
            print(f"  {name}: NOT FOUND"); continue
        t = mt5.symbol_info_tick(name)
        r = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_D1, 0, 6000)
        d1n, d1a, d1b = 0, "", ""
        if r is not None and len(r):
            ts = pd.to_datetime(pd.DataFrame(r)["time"], unit="s", utc=True)
            d1n, d1a, d1b = len(r), str(ts.min().date()), str(ts.max().date())
        rec = {
            "symbol": i.name, "description": i.description,
            "trade_contract_size": i.trade_contract_size,
            "trade_tick_size": i.trade_tick_size,
            "trade_tick_value": i.trade_tick_value,
            "trade_tick_value_profit": getattr(i, "trade_tick_value_profit", float("nan")),
            "trade_tick_value_loss": getattr(i, "trade_tick_value_loss", float("nan")),
            "point": i.point, "digits": i.digits,
            "currency_base": i.currency_base, "currency_profit": i.currency_profit,
            "currency_margin": i.currency_margin,
            "swap_mode": SM.get(i.swap_mode, str(i.swap_mode)),
            "swap_mode_raw": i.swap_mode,
            "swap_long": i.swap_long, "swap_short": i.swap_short,
            "swap_rollover3days": i.swap_rollover3days,
            "volume_min": i.volume_min, "volume_step": i.volume_step,
            "volume_max": i.volume_max,
            "bid": getattr(t, "bid", float("nan")), "ask": getattr(t, "ask", float("nan")),
            "calc_mode": CM.get(i.trade_calc_mode, str(i.trade_calc_mode)),
            "d1_bars": d1n, "d1_from": d1a, "d1_to": d1b,
        }
        rows.append(rec)
        print(f"  {i.name:<12} contract={i.trade_contract_size:<10g} "
              f"tick_size={i.trade_tick_size:<10g} tick_value={i.trade_tick_value:<10g} "
              f"swap={SM.get(i.swap_mode)} L={i.swap_long} S={i.swap_short} "
              f"r3d={i.swap_rollover3days} D1={d1n} from={d1a}")

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "FROZEN_SYMBOL_SPECS.csv", index=False)

    # ---- EMPIRICAL: any completed deal with NONZERO swap is the only real verification
    print("\nDEALS WITH NONZERO SWAP (empirical verification of the conversion):")
    frm = datetime.now(timezone.utc) - timedelta(days=400)
    to = datetime.now(timezone.utc) + timedelta(days=1)
    deals = mt5.history_deals_get(frm, to)
    hits = []
    if deals:
        for d in deals:
            if abs(getattr(d, "swap", 0.0)) > 1e-9:
                hits.append({"ticket": d.ticket, "order": d.order, "position_id": d.position_id,
                             "symbol": d.symbol, "type": d.type, "volume": d.volume,
                             "price": d.price, "swap": d.swap, "profit": d.profit,
                             "commission": d.commission,
                             "time": str(pd.to_datetime(d.time, unit="s", utc=True))})
    if hits:
        pd.DataFrame(hits).to_csv(OUT / "DEALS_WITH_SWAP.csv", index=False)
        for h in hits[:20]:
            print(f"  {h['symbol']:<12} vol={h['volume']:<6} swap={h['swap']:>10.4f} "
                  f"{h['time']}")
        print(f"  -> {len(hits)} deals with swap  ->  DEALS_WITH_SWAP.csv")
    else:
        n = len(deals) if deals else 0
        print(f"  NONE. {n} deals in 400 days, none carried swap.")
        print("  -> swap conversion can only be MEASURED_METADATA_ONLY, never VERIFIED.")

    json.dump({"login": a.login, "server": a.server,
               "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "n_symbols": len(rows), "n_deals_with_swap": len(hits)},
              open(OUT / "FROZEN_SYMBOL_SPECS_META.json", "w"), indent=1)
    print(f"\nwritten -> {OUT}\\FROZEN_SYMBOL_SPECS.csv")
    mt5.shutdown()


if __name__ == "__main__":
    main()
