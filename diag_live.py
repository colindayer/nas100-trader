"""
diag_live.py — why isn't anything firing live? Dumps the ACTUAL hours present in
the live MT5 bars, because every strategy keys off specific ET hours:
  S5 ORB   needs the 9:00 ET bar        (or_bar = bars[bars.index.hour == 9])
  S1/S4    need the Asian session       (18:00-02:00 ET)
If the live MT5 feed doesn't produce those exact ET hours, the strategies skip
every run and you get silence even though verify_liveness (CSV data) fires.

Run on the VPS:  python diag_live.py
"""
from mt5_broker import MT5Broker

b = MT5Broker()
for internal in ("QQQ", "SPY", "GLD"):
    try:
        df = b.get_bars(internal, "1Hour", 72)
    except Exception as e:
        print(f"{internal}: get_bars FAILED — {type(e).__name__}: {e}")
        continue
    mapped = b.map(internal)
    hours = sorted(set(int(h) for h in df.index.hour))
    has9 = 9 in hours
    has_asian = any(h >= 18 or h < 2 for h in hours)
    print(f"\n=== {internal} -> {mapped} | {len(df)} bars | tz={df.index.tz} ===")
    print("last 8 bars (should read as ET local time):")
    for ix, row in df.tail(8).iterrows():
        print(f"   {ix}   hour(ET)={ix.hour:2d}   O={row['Open']:.1f} C={row['Close']:.1f}")
    print(f"distinct ET hours present: {hours}")
    print(f"  has 9:00 ET bar (S5 ORB needs it)?   {'YES' if has9 else 'NO  <-- S5 can never fire'}")
    print(f"  has Asian 18-02 ET (S1/S4 need it)?  {'YES' if has_asian else 'NO  <-- S1/S4 can never fire'}")

print("\nIf hours look shifted (e.g. ORB bar shows as 8 or 10, not 9), the MT5 "
      "server->UTC->ET rebasing is off by that many hours — fix server_utc_offset "
      "in config.ini [mt5]. If bars stop well before 9 ET, the feed lookback/session "
      "doesn't reach the opening range.")
