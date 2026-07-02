"""
fetch_mt5_history.py — THE DATA BRIDGE: export deep hourly history from the
MT5 terminal (FundedNext/FTMO/demo) into CSVs compatible with every backtest
and validation tool in this repo.

WHY: broker-real CFD data (US100/XAUUSD/BTCUSD) includes the OVERNIGHT session
that yfinance ETFs lack — FINDINGS.md showed the sweep edge NEEDS the overnight
session (futures rescued the 'failed' cash-index tests). Validating on the MT5
feed = validating on the exact instrument, spreads and sessions you'll trade
in the challenge. Also: no rate limits, no geo-blocks, free with the account.

Run ON THE WINDOWS VPS where the MT5 terminal is logged in:
    pip install MetaTrader5 pandas pytz
    python fetch_mt5_history.py                       # US100 + XAUUSD + BTCUSD, 4y H1
    python fetch_mt5_history.py --symbols US100 --years 6
    python fetch_mt5_history.py --symbols US100 --alias qqq
        (--alias also writes qqq_hourly_7y.csv so verify_liveness.py /
         intraday_momentum_test.py replay their logic on the CFD feed directly)

Output: {symbol}_hourly_mt5.csv with columns
    timestamp (UTC), symbol, open, high, low, close, volume
NOTE: 'volume' is MT5 TICK volume (CFDs have no centralized real volume). It's
a standard proxy; S5's volume-confirmation ratio works on it, but treat any
volume-sensitive result with one extra grain of salt.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

CHUNK_DAYS = 90          # fetch window per request (kind to the terminal)


def connect():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("MetaTrader5 package missing (Windows only): pip install MetaTrader5")
    from broker import load_config
    cfg = load_config("mt5")
    login, passwd, server = cfg.get("login", ""), cfg.get("password", ""), cfg.get("server", "")
    if login and not login.startswith("YOUR_"):
        ok = mt5.initialize(login=int(login), password=passwd, server=server)
    else:
        ok = mt5.initialize()   # attach to the already-running, logged-in terminal
    if not ok:
        sys.exit(f"MT5 initialize failed: {mt5.last_error()} — is the terminal "
                 f"running and logged in on this machine?")
    info = mt5.account_info()
    print(f"Connected: server={getattr(info, 'server', '?')} "
          f"login={getattr(info, 'login', '?')} equity={getattr(info, 'equity', '?')}")
    return mt5


def fetch_symbol(mt5, sym, years):
    if not mt5.symbol_select(sym, True):
        print(f"  ⚠️ '{sym}' not on this broker — run `python mt5_broker.py` to "
              f"list symbol names, then retry with the right one")
        return None
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(years * 365.25))
    frames = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=CHUNK_DAYS), end)
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, cur, nxt)
        if rates is not None and len(rates):
            frames.append(pd.DataFrame(rates))
        cur = nxt
    if not frames:
        print(f"  ⚠️ {sym}: no H1 history returned — broker may limit depth; "
              f"try fewer --years, or open a {sym} H1 chart in the terminal and "
              f"scroll back once to force a history download, then re-run")
        return None
    df = pd.concat(frames).drop_duplicates(subset="time").sort_values("time")
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df["time"], unit="s", utc=True),
        "symbol": sym,
        "open": df["open"], "high": df["high"], "low": df["low"],
        "close": df["close"], "volume": df["tick_volume"],
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["US100", "XAUUSD", "BTCUSD"])
    ap.add_argument("--years", type=float, default=4)
    ap.add_argument("--alias", default=None,
                    help="also save the FIRST symbol as {alias}_hourly_7y.csv "
                         "(so QQQ-based tools replay on the CFD feed)")
    args = ap.parse_args()

    mt5 = connect()
    first_df = None
    for sym in args.symbols:
        print(f"\nFetching {sym} H1, {args.years:g}y …")
        df = fetch_symbol(mt5, sym, args.years)
        if df is None:
            continue
        path = f"{sym.lower()}_hourly_mt5.csv"
        df.to_csv(path, index=False)
        span = f"{df['timestamp'].iloc[0]:%Y-%m-%d} → {df['timestamp'].iloc[-1]:%Y-%m-%d}"
        print(f"  ✅ {path}: {len(df):,} bars  ({span})")
        if first_df is None:
            first_df = (sym, df)
    if args.alias and first_df is not None:
        sym, df = first_df
        alias_path = f"{args.alias.lower()}_hourly_7y.csv"
        d2 = df.copy()
        d2["symbol"] = args.alias.upper()   # so load('<ALIAS>') keeps the rows
        d2.to_csv(alias_path, index=False)
        print(f"\n  ✅ alias: {alias_path} (= {sym} data) → now you can run "
              f"verify_liveness.py / intraday_momentum_test.py on the CFD feed")
    mt5.shutdown()
    print("\nDone. Next: python verify_liveness.py   (proves the entry logic "
          "fires on the broker's own data)")


if __name__ == "__main__":
    main()
