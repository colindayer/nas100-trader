"""
fetch_dukascopy.py — Download free M1 OHLCV data from Dukascopy public datafeed.

Source: https://datafeed.dukascopy.com/datafeed/{INSTRUMENT}/{Y}/{M:02d}/{D:02d}/{H:02d}h_ticks.bi5
Format: LZMA-compressed binary (BI5). Each tick = 5 big-endian int32:
  [time_ms_in_hour, ask*10, bid*10, ask_vol*100, bid_vol*100]
Mid = (ask + bid) / 2.  Prices divided by 10 (no further scaling for indices).

License: Dukascopy provides this data free for personal/research use.
Do NOT redistribute raw files. See SETUP.md for full terms.

Instruments verified in Dukascopy JForex symbol list:
  NAS100USD  — Nasdaq-100 index (CFD, USD-quoted, point = 1 USD)
  XAUUSD     — Gold spot (USD per troy oz)

Usage:
  python fetch_dukascopy.py --instrument NAS100USD --year 2024
  python fetch_dukascopy.py --instrument XAUUSD --start 2023-01-01 --end 2024-12-31
  python fetch_dukascopy.py --all          # all instruments, 2019-2025
"""

import argparse
import io
import lzma
import os
import struct
import time
from datetime import date, timedelta, datetime

import pandas as pd
import requests

BASE_URL = "https://datafeed.dukascopy.com/datafeed"

INSTRUMENTS = {
    "NAS100USD": {"file": "nas100_m1", "price_div": 10.0},
    "XAUUSD":    {"file": "xauusd_m1", "price_div": 100_000.0},
}

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _url(instrument: str, y: int, m: int, d: int, h: int) -> str:
    return f"{BASE_URL}/{instrument}/{y}/{m-1:02d}/{d:02d}/{h:02d}h_ticks.bi5"


def _decode_bi5(raw: bytes, price_div: float, base_dt: datetime) -> list:
    """Decode a BI5 payload: list of (timestamp_ms, ask, bid, ask_vol, bid_vol)."""
    if not raw:
        return []
    data = lzma.decompress(raw)
    ticks = []
    record_size = 20  # 5 × int32 = 20 bytes
    for i in range(0, len(data) - record_size + 1, record_size):
        t_ms, ask_raw, bid_raw, avol_raw, bvol_raw = struct.unpack_from(">iiiii", data, i)
        ts  = base_dt + timedelta(milliseconds=t_ms)
        ask = ask_raw / price_div
        bid = bid_raw / price_div
        mid = (ask + bid) / 2.0
        avol = avol_raw / 100.0
        bvol = bvol_raw / 100.0
        ticks.append((ts, mid, ask, bid, avol + bvol))
    return ticks


def fetch_hour(instrument: str, y: int, m: int, d: int, h: int,
               price_div: float, session: requests.Session) -> list:
    url  = _url(instrument, y, m, d, h)
    base = datetime(y, m, d, h, 0, 0)
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return _decode_bi5(resp.content, price_div, base)
    except Exception as e:
        print(f"    WARN {url}: {e}")
        return []


def ticks_to_m1(ticks: list) -> pd.DataFrame:
    """Aggregate tick list to 1-minute OHLCV bars."""
    if not ticks:
        return pd.DataFrame()
    df = pd.DataFrame(ticks, columns=["ts", "mid", "ask", "bid", "vol"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts")
    ohlcv = df["mid"].resample("1min").ohlcv() if hasattr(df["mid"].resample("1min"), "ohlcv") else (
        df["mid"].resample("1min").agg(open="first", high="max", low="min", close="last")
    )
    ohlcv["volume"] = df["vol"].resample("1min").sum()
    ohlcv = ohlcv.dropna(subset=["open"])
    return ohlcv


def fetch_day(instrument: str, dt: date, price_div: float,
              session: requests.Session) -> pd.DataFrame:
    all_ticks = []
    for h in range(24):
        ticks = fetch_hour(instrument, dt.year, dt.month, dt.day, h, price_div, session)
        all_ticks.extend(ticks)
        if ticks:
            time.sleep(0.05)  # be polite — 50ms between requests
    return ticks_to_m1(all_ticks)


def fetch_range(instrument: str, start: date, end: date) -> None:
    info      = INSTRUMENTS[instrument]
    price_div = info["price_div"]
    file_stem = info["file"]
    os.makedirs(OUT_DIR, exist_ok=True)

    years = range(start.year, end.year + 1)
    session = requests.Session()
    session.headers["User-Agent"] = "research-bot/1.0"

    for year in years:
        y_start = max(start, date(year, 1, 1))
        y_end   = min(end,   date(year, 12, 31))
        out_path = os.path.join(OUT_DIR, f"{file_stem}_{year}.parquet")

        if os.path.exists(out_path):
            print(f"  {year}: {out_path} already exists — skip (delete to re-download)")
            continue

        print(f"  {instrument} {year}: {y_start} → {y_end}")
        frames = []
        cur = y_start
        while cur <= y_end:
            if cur.weekday() < 5:  # Mon-Fri only
                print(f"    {cur} ...", end="", flush=True)
                df = fetch_day(instrument, cur, price_div, session)
                if not df.empty:
                    frames.append(df)
                    print(f" {len(df)} bars")
                else:
                    print(" (holiday/no data)")
            cur += timedelta(days=1)

        if frames:
            combined = pd.concat(frames).sort_index()
            combined.index = pd.to_datetime(combined.index, utc=True)
            combined.to_parquet(out_path)
            print(f"  Saved {len(combined):,} M1 bars → {out_path}")
        else:
            print(f"  {year}: no data downloaded")


def main():
    parser = argparse.ArgumentParser(description="Download Dukascopy M1 data")
    parser.add_argument("--instrument", choices=list(INSTRUMENTS.keys()),
                        help="Instrument name (e.g. NAS100USD, XAUUSD)")
    parser.add_argument("--year", type=int, help="Single year to download")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   help="End date YYYY-MM-DD")
    parser.add_argument("--all", action="store_true",
                        help="Download all instruments, 2019-2025")
    args = parser.parse_args()

    if args.all:
        for inst in INSTRUMENTS:
            print(f"\n=== {inst} ===")
            fetch_range(inst, date(2019, 1, 1), date(2025, 12, 31))
        return

    if not args.instrument:
        parser.error("--instrument required unless --all is used")

    if args.year:
        fetch_range(args.instrument, date(args.year, 1, 1), date(args.year, 12, 31))
    elif args.start and args.end:
        fetch_range(args.instrument,
                    date.fromisoformat(args.start), date.fromisoformat(args.end))
    else:
        parser.error("Provide --year or both --start and --end")


if __name__ == "__main__":
    main()
