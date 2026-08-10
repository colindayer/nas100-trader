"""METADATA-ONLY probe. No history calls, no downloads, no disk growth. ~30 seconds.

    py scripts\\broker_probe_meta.py

WHY THIS EXISTS
  The full probe made MT5 download D1+H1 for 166 symbols and filled a 48 GB disk (26.5 GB of
  `bases` cache), then lost every measured row to ENOSPC at the final write.

  But the two halves have completely different costs:
      history depth  -> needs a rates call   -> triggers a multi-GB server download
      contract specs -> symbol_info() only  -> instant, zero bytes

  The depths were already measured and are stored in data/universe/FTMO_HISTORY_DEPTH.json.
  This script fetches ONLY the specs and merges them. Nothing is re-downloaded.

  Contains no trading calls and no rates call of any kind. The scan asserts it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 required")
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe"
DEPTH = ROOT / "broker" / "FTMO_HISTORY_DEPTH.json"

TM = {0: "DISABLED", 1: "LONGONLY", 2: "SHORTONLY", 3: "CLOSEONLY", 4: "FULL"}
EM = {0: "REQUEST", 1: "INSTANT", 2: "MARKET", 3: "EXCHANGE"}
SM = {0: "DISABLED", 1: "POINTS", 2: "SYMBOL_CURRENCY", 3: "MARGIN_CURRENCY",
      4: "DEPOSIT_CURRENCY", 5: "INT_CURRENT", 6: "INT_OPEN", 7: "REOPEN_CURRENT",
      8: "REOPEN_BID"}
CM = {0: "FOREX", 1: "FUTURES", 2: "CFD", 3: "CFDINDEX", 4: "CFDLEVERAGE",
      5: "FOREX_NO_LEV", 32: "EXCH_STOCKS", 33: "EXCH_FUTURES", 35: "EXCH_BONDS"}


def bound():
    lg = sv = None
    for line in (ROOT / "config" / "guardian.env").read_text().splitlines():
        s = line.strip()
        if s.startswith("ACCOUNT_LOGIN"):
            lg = int(s.split("=", 1)[1].strip())
        elif s.startswith("ACCOUNT_SERVER_CONTAINS"):
            sv = s.split("=", 1)[1].strip().upper()
    return lg, sv


def main():
    if not mt5.initialize():
        sys.exit(f"initialize failed: {mt5.last_error()}")
    a = mt5.account_info()
    if a is None:
        mt5.shutdown(); sys.exit("HALT: not logged in")
    print(f"connected: login={a.login} server={a.server}")
    wl, ws = bound()
    if int(a.login) != wl or ws not in str(a.server).upper():
        mt5.shutdown()
        sys.exit(f"HALT (fail-closed): bound to {wl}/~{ws}, connected to {a.login}/{a.server}")
    print(f"IDENTITY OK -> {a.login}\n")

    depths = {}
    if DEPTH.exists():
        depths = json.load(open(DEPTH))["bars"]
        print(f"merging {len(depths)} previously MEASURED history depths "
              f"(no re-download)\n")
    else:
        print("WARNING: no FTMO_HISTORY_DEPTH.json — depths will be blank\n")

    rows = []
    for s in mt5.symbols_get():
        i = mt5.symbol_info(s.name)
        if i is None:
            continue
        t = mt5.symbol_info_tick(s.name)
        dep = depths.get(i.name, {})
        rows.append({
            "symbol": i.name, "description": i.description, "path": i.path,
            "sector": getattr(i, "sector_name", ""), "exchange": getattr(i, "exchange", ""),
            "calc_mode": CM.get(i.trade_calc_mode, str(i.trade_calc_mode)),
            "currency_base": i.currency_base, "currency_profit": i.currency_profit,
            "contract_size": i.trade_contract_size, "digits": i.digits, "point": i.point,
            "tick_size": i.trade_tick_size, "tick_value": i.trade_tick_value,
            "volume_min": i.volume_min, "volume_max": i.volume_max,
            "volume_step": i.volume_step, "spread_points": i.spread,
            "spread_price": i.spread * i.point,
            "bid": getattr(t, "bid", float("nan")), "ask": getattr(t, "ask", float("nan")),
            "trade_mode": TM.get(i.trade_mode, str(i.trade_mode)),
            "execution_mode": EM.get(i.trade_exemode, str(i.trade_exemode)),
            "swap_long": i.swap_long, "swap_short": i.swap_short,
            "swap_mode": SM.get(i.swap_mode, str(i.swap_mode)),
            "swap_rollover3days": i.swap_rollover3days, "margin_initial": i.margin_initial,
            "was_visible": bool(i.visible),
            "d1_bars": dep.get("d1_bars", 0), "d1_from": "", "d1_to": "",
            "h1_bars": dep.get("h1_bars", 0),
            "history_latency_s": float("nan"), "history_attempts": 0,
            "history_source": "measured 2026-08-09/10" if dep else "NOT MEASURED",
        })

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = str(a.server).replace(" ", "_")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    df.to_csv(OUT / f"BROKER_RAW_{tag}.csv", index=False)
    df.to_csv(OUT / f"BROKER_RAW_{tag}_{stamp}.csv", index=False)
    json.dump({"login": a.login, "server": a.server, "company": a.company,
               "currency": a.currency, "captured_utc": stamp, "n_symbols": len(df),
               "note": "specs live; history depth merged from the 2026-08-09/10 measurement"},
              open(OUT / f"BROKER_META_{tag}.json", "w"), indent=1)

    print(f"{len(df)} symbols  |  {int((df.d1_bars > 0).sum())} with measured history")
    print(f"written -> {OUT}\\BROKER_RAW_{tag}.csv  ({df.memory_usage(deep=True).sum()/1e6:.2f} MB)")
    print(f"next: py scripts\\broker_report.py")
    mt5.shutdown()


if __name__ == "__main__":
    main()
