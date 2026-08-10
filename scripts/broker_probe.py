"""BROKER PROBE — emits the raw capture that BrokerProfile consumes. Runs on the VPS.

    py scripts/broker_probe.py                 # bound to the configured account
    py scripts/broker_probe.py --any-account   # explicit opt-out, for profiling OTHER brokers

READ-ONLY except symbol_select(), which is authorised for this job and restored at the end.
This file contains no trading calls; tests/test_broker_probe_safety.py asserts that.

WHAT v2 GOT WRONG AND THIS FIXES
  v2 called copy_rates_from_pos() immediately after symbol_select() and got ZERO bars for all
  166 FTMO symbols. MT5 fetches history ASYNCHRONOUSLY: selecting a symbol only queues the
  request. The first call almost always returns empty. This polls with exponential backoff
  until bars appear or a timeout, and records the latency so history availability becomes a
  measured property of the broker rather than an assumption.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 package required — run on the Windows VPS")
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "universe"

HISTORY_TIMEOUT_S = 6.0

# MT5 returns None when the requested count EQUALS terminal_info().maxbars (typically 100000).
# v2 and the first version of this probe both hardcoded 100000 and read the resulting None as
# "no history", reporting 0 bars for all 166 FTMO symbols. XAUUSD in fact serves 5000+ bars on
# the FIRST call with no wait. Diagnosed 2026-08-09. Request is now clamped below maxbars.
# Requesting 50000 H1 bars (~20 years) forces the terminal to DOWNLOAD that history from the
# server before returning, per symbol. On 166 cold symbols the probe blocked with near-zero CPU.
# D1 depth is what the trend strategy needs; H1 only needs to be shown to exist.
MAX_BARS_D1 = 6000        # ~24 years of daily -- more than any CFD history
MAX_BARS_H1 = 2000        # ~3 months of hourly -- enough to prove availability

# Measured 2026-08-09 on FTMO-Demo: these are LISTED but serve ZERO bars, and each burns
# ~250-345s inside ONE uninterruptible copy_rates call. Skipping them turns a 2-hour run into
# ~40 minutes. They are still recorded, with d1_bars=0 and history_skipped=True, because
# "listed but no data" is itself a broker capability finding.
KNOWN_NO_HISTORY = {
    "SOLUSD", "AVAUSD", "ETCUSD", "DOGEUSD", "XMRUSD", "BNBUSD", "SANUSD", "LNKUSD",
    "NERUSD", "ALGUSD", "ICPUSD", "AAVUSD", "BARUSD", "GALUSD", "GRTUSD", "MANUSD",
    "XLMUSD", "UNIUSD", "XTZUSD",
}
BACKOFF = (0.05, 0.15, 0.4, 1.0, 2.0, 4.0)

TM = {0: "DISABLED", 1: "LONGONLY", 2: "SHORTONLY", 3: "CLOSEONLY", 4: "FULL"}
EM = {0: "REQUEST", 1: "INSTANT", 2: "MARKET", 3: "EXCHANGE"}
SM = {0: "DISABLED", 1: "POINTS", 2: "SYMBOL_CURRENCY", 3: "MARGIN_CURRENCY",
      4: "DEPOSIT_CURRENCY", 5: "INT_CURRENT", 6: "INT_OPEN", 7: "REOPEN_CURRENT",
      8: "REOPEN_BID"}
CM = {0: "FOREX", 1: "FUTURES", 2: "CFD", 3: "CFDINDEX", 4: "CFDLEVERAGE",
      5: "FOREX_NO_LEV", 32: "EXCH_STOCKS", 33: "EXCH_FUTURES", 35: "EXCH_BONDS"}


def bound_identity():
    login = server = None
    try:
        for line in (ROOT / "config" / "guardian.env").read_text().splitlines():
            s = line.strip()
            if s.startswith("ACCOUNT_LOGIN"):
                login = int(s.split("=", 1)[1].strip())
            elif s.startswith("ACCOUNT_SERVER_CONTAINS"):
                server = s.split("=", 1)[1].strip().upper()
    except Exception:
        pass
    return login, server


def _bar_cap(want: int) -> int:
    """Stay strictly BELOW the terminal's maxbars: requesting exactly maxbars returns None."""
    try:
        mb = int(getattr(mt5.terminal_info(), "maxbars", 0) or 0)
    except Exception:
        mb = 0
    return max(500, min(want, mb - 1)) if mb else want


def history_with_backoff(symbol: str, timeframe, timeout=HISTORY_TIMEOUT_S, want=MAX_BARS_D1):
    """Poll until history materialises. Returns (bars, first, last, latency_s, attempts)."""
    cap = _bar_cap(want)
    t0 = time.time()
    for attempt, wait in enumerate(BACKOFF + (0.0,) * 40, 1):
        try:
            r = mt5.copy_rates_from_pos(symbol, timeframe, 0, cap)
        except Exception:
            r = None
        if r is not None and len(r):
            t = pd.to_datetime(pd.DataFrame(r)["time"], unit="s", utc=True)
            return len(r), str(t.min().date()), str(t.max().date()), time.time() - t0, attempt
        if time.time() - t0 > timeout:
            return 0, "", "", time.time() - t0, attempt
        time.sleep(wait if wait else 0.5)
    return 0, "", "", time.time() - t0, len(BACKOFF)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--any-account", action="store_true",
                    help="profile whatever account is connected (for cross-broker comparison)")
    ap.add_argument("--max-symbols", type=int, default=0)
    a = ap.parse_args()

    if not mt5.initialize():
        sys.exit(f"initialize failed: {mt5.last_error()}")
    acct = mt5.account_info()
    if acct is None:
        mt5.shutdown(); sys.exit("HALT: not logged in")
    print(f"connected: login={acct.login} server={acct.server} company={acct.company}")

    want_login, want_server = bound_identity()
    if not a.any_account:
        if want_login is None or not want_server:
            mt5.shutdown(); sys.exit("HALT: guardian.env has no ACCOUNT_LOGIN/SERVER binding")
        if int(acct.login) != want_login or want_server not in str(acct.server).upper():
            mt5.shutdown()
            sys.exit(f"HALT (fail-closed): bound to login={want_login} server~{want_server}, "
                     f"connected to login={acct.login} server={acct.server}. "
                     f"Nothing selected or modified. Use --any-account to profile deliberately.")
        print(f"IDENTITY OK -> {acct.login}")
    else:
        print("--any-account: identity check WAIVED deliberately (cross-broker profiling)")
    print(f"balance {acct.balance:.2f} {acct.currency}\n")

    # A full capture died at the final write with ENOSPC after two hours of measurement.
    # Check before starting, not after.
    import shutil
    OUT.mkdir(parents=True, exist_ok=True)
    free_mb = shutil.disk_usage(OUT).free / 1e6
    print(f"free disk at output path: {free_mb:,.0f} MB")
    if free_mb < 50:
        mt5.shutdown()
        sys.exit(f"HALT: only {free_mb:.0f} MB free. Free space before running -- the previous "
                 f"capture lost 2 hours of work to ENOSPC at the final write.")

    syms = mt5.symbols_get()
    if a.max_symbols:
        syms = syms[:a.max_symbols]
    print(f"{len(syms)} symbols\n")
    was_visible = {s.name: bool(s.visible) for s in syms}

    rows, added = [], []
    t_start = time.time()
    for i, s in enumerate(syms, 1):
        inf = mt5.symbol_info(s.name)
        if inf is None:
            continue
        if not inf.visible and mt5.symbol_select(inf.name, True):
            added.append(inf.name)
            inf = mt5.symbol_info(inf.name)
        tk = mt5.symbol_info_tick(inf.name)
        if inf.name.upper() in KNOWN_NO_HISTORY:
            d1n, d1a, d1b, lat, att, skipped = 0, "", "", 0.0, 0, True
        else:
            d1n, d1a, d1b, lat, att = history_with_backoff(inf.name, mt5.TIMEFRAME_D1,
                                                           want=MAX_BARS_D1)
            skipped = False
        h1n, _, _, _, _ = (history_with_backoff(inf.name, mt5.TIMEFRAME_H1, timeout=4.0,
                                                want=MAX_BARS_H1) if d1n
                           else (0, "", "", 0.0, 0))
        print(f"  [{i:>3}/{len(syms)}] {inf.name:<16} D1 {d1n:>6}  H1 {h1n:>6}  "
              f"{lat:>5.2f}s", flush=True)
        rows.append({
            "symbol": inf.name, "description": inf.description, "path": inf.path,
            "sector": getattr(inf, "sector_name", ""), "exchange": getattr(inf, "exchange", ""),
            "calc_mode": CM.get(inf.trade_calc_mode, str(inf.trade_calc_mode)),
            "currency_base": inf.currency_base, "currency_profit": inf.currency_profit,
            "contract_size": inf.trade_contract_size, "digits": inf.digits, "point": inf.point,
            "tick_size": inf.trade_tick_size, "tick_value": inf.trade_tick_value,
            "volume_min": inf.volume_min, "volume_max": inf.volume_max,
            "volume_step": inf.volume_step, "spread_points": inf.spread,
            "spread_price": inf.spread * inf.point,
            "bid": getattr(tk, "bid", float("nan")), "ask": getattr(tk, "ask", float("nan")),
            "trade_mode": TM.get(inf.trade_mode, str(inf.trade_mode)),
            "execution_mode": EM.get(inf.trade_exemode, str(inf.trade_exemode)),
            "swap_long": inf.swap_long, "swap_short": inf.swap_short,
            "swap_mode": SM.get(inf.swap_mode, str(inf.swap_mode)),
            "swap_rollover3days": inf.swap_rollover3days,
            "margin_initial": inf.margin_initial, "was_visible": was_visible.get(inf.name, False),
            "d1_bars": d1n, "d1_from": d1a, "d1_to": d1b, "h1_bars": h1n,
            "history_latency_s": round(lat, 3), "history_attempts": att,
            "history_skipped": skipped,
        })
        # INCREMENTAL WRITE. The previous run measured all 166 symbols and lost every one of
        # them because the only write was at the end and the disk was full.
        if i % 10 == 0 or i == len(syms):
            try:
                pd.DataFrame(rows).to_csv(OUT / f"BROKER_RAW_{str(acct.server).replace(' ','_')}"
                                                f".partial.csv", index=False)
            except OSError as e:
                print(f"  !! partial write failed: {e}", flush=True)
        if i % 25 == 0:
            ok = sum(1 for r in rows if r["d1_bars"] > 0)
            print(f"  --- {i}/{len(syms)}  history {ok}/{len(rows)}  "
                  f"{time.time()-t_start:.0f}s elapsed", flush=True)

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = str(acct.server).replace(" ", "_")
    df.to_csv(OUT / f"BROKER_RAW_{tag}.csv", index=False)
    df.to_csv(OUT / f"BROKER_RAW_{tag}_{stamp}.csv", index=False)
    json.dump({"login": acct.login, "server": acct.server, "company": acct.company,
               "currency": acct.currency, "captured_utc": stamp, "n_symbols": len(df),
               "selected_added": len(added),
               "history_timeout_s": HISTORY_TIMEOUT_S}, 
              open(OUT / f"BROKER_META_{tag}.json", "w"), indent=1)

    got = df[df.d1_bars > 0]
    print(f"\nHISTORY: {len(got)}/{len(df)} symbols returned bars "
          f"({len(got)/max(len(df),1):.0%} success)")
    if len(got):
        print(f"  latency  median {got.history_latency_s.median():.2f}s  "
              f"p90 {got.history_latency_s.quantile(0.9):.2f}s  "
              f"max {got.history_latency_s.max():.2f}s")
        print(f"  attempts median {got.history_attempts.median():.0f}")
        print(f"  D1 bars  median {got.d1_bars.median():.0f}  max {got.d1_bars.max():.0f}")
        print(f"  earliest {got.d1_from.min()}")
    fail = df[df.d1_bars == 0]
    if len(fail):
        print(f"  NO HISTORY ({len(fail)}): {', '.join(fail.symbol.head(8))}"
              f"{' ...' if len(fail) > 8 else ''}")

    for s in added:
        try:
            mt5.symbol_select(s, False)
        except Exception:
            pass
    print(f"\nMarket Watch restored: deselected {len(added)}")
    print(f"written -> {OUT}/BROKER_RAW_{tag}.csv")
    print(f"next (anywhere): py scripts/broker_report.py")
    mt5.shutdown()


if __name__ == "__main__":
    main()
