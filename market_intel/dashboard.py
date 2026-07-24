"""dashboard.py -- PHASE 701 live intelligence dashboard (text). Read-only view.
Run:  py -m market_intel.dashboard --symbols EURUSD,XAUUSD,NAS100
"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone, timedelta
from . import calendar_feed as cal
from .engine import scan, INTEL_LOG
from .opportunity import OpportunityRegistry


def _mt5_bars(symbol):
    import MetaTrader5 as mt5, pandas as pd
    if not mt5.initialize(): raise SystemExit("MT5 unavailable")
    def grab(tf, n):
        r = mt5.copy_rates_from_pos(symbol, tf, 0, n)
        if r is None or not len(r): return None
        d = pd.DataFrame(r); d["time"] = pd.to_datetime(d["time"], unit="s", utc=True)
        return d.set_index("time")[["open", "high", "low", "close"]]
    return grab(mt5.TIMEFRAME_M5, 600), grab(mt5.TIMEFRAME_D1, 90)


def render(symbols):
    now = datetime.now(timezone.utc)
    events = cal.load()
    print("=" * 74)
    print(f" MARKET INTELLIGENCE  {now:%Y-%m-%d %H:%M UTC}    EXECUTION STATUS: SHADOW (no orders)")
    print("=" * 74)
    for sym in symbols:
        try:
            m5, d1 = _mt5_bars(sym)
            if m5 is None or d1 is None:
                print(f"\n{sym}: no data"); continue
            r = scan(sym, m5, d1, events=events, now=now)
            s = r["state"]
            print(f"\n{sym}  {s.price:.5f}")
            print(f"  regime      : trend={s.trend} ({s.trend_strength:+.4f})  vol={s.volatility_regime}  ATR={s.atr:.5f}")
            print(f"  session     : {s.session}   kill_zones: {','.join(s.kill_zones) or 'none'}")
            print(f"  structure   : {s.structure}  sweep={s.liquidity_sweep}  fvg={s.fvg}  ob={s.order_block}")
            print(f"  levels      : PDH {s.prev_day_high:.5f} / PDL {s.prev_day_low:.5f} | "
                  f"OR {s.opening_range_low:.5f}-{s.opening_range_high:.5f} | VWAP {s.vwap:.5f}")
            for o in r["opportunities"]:
                print(f"  OPPORTUNITY : {o.instrument} dir={o.direction:+d} conf={o.confidence:.2f} "
                      f"[{o.status}]  {o.economic_reasoning}")
        except Exception as e:
            print(f"\n{sym}: error {e}")

    up = cal.upcoming(events, now=now, hours=48)
    print("\n" + "-" * 74)
    print(" UPCOMING ECONOMIC EVENTS (48h)")
    if not up:
        print("   none loaded — supply market_intel/calendar.csv or an MT5 build with calendar support")
    for e in up[:12]:
        try:
            t = datetime.fromisoformat(e.scheduled.replace("Z", "+00:00"))
            mins = int((t - now).total_seconds() // 60)
            cd = f"T-{mins//60}h{mins%60:02d}m" if mins > 0 else "DUE"
        except Exception:
            cd = "?"
        print(f"   {cd:>10}  {e.impact.upper():<6} {e.currency:<4} {e.name:<34} "
              f"prev={e.previous} fcst={e.forecast} actual={e.actual}")

    rel = [e for e in cal.just_released(events)][-5:]
    if rel:
        print("\n LATEST RELEASES")
        for e in rel:
            s = e.surprise()
            print(f"   {e.currency} {e.name}: actual={e.actual} fcst={e.forecast} "
                  f"surprise={s:+.4g} ({(e.surprise_pct() or 0):+.1%})")

    opps = OpportunityRegistry().all()
    print("\n OPPORTUNITY REGISTRY: "
          f"{len(opps)} total | shadow-allowed {sum(1 for o in opps if o['status']=='SHADOW_ALLOWED')} "
          f"| rejected {sum(1 for o in opps if o['status']=='REJECTED')}")
    # PHASE 702.1: query the REAL components instead of asserting "not wired"
    try:
        from execution_safety.promotion_pipeline_v2 import evaluate, REQUIREMENTS
        st = evaluate("portfolio_multisleeve")
        print(f"\n BELIEF  research {st['research_belief']:.4f} (live bar 0.60) | "
              f"operational {st['operational_belief']:.4f} (live bar 0.85)")
        print(f" STATE   {st['state']}  ->  next: {st['next_state']}")
        print(f"         demo_trades={st['demo_trades']}  position_cap={st['position_cap']}  "
              f"risk/trade={st['risk_cap_pct']:.2%}")
        for gate, need in st["blocking"].items():
            print(f"         blocking {gate}: {'; '.join(need)}")
        if st["outstanding_defects"]:
            print(f"         DEFECTS: {len(st['outstanding_defects'])}")
    except Exception as e:
        print(f"\n BELIEF  unavailable: {e} (run from the repo root so execution_safety/ is importable)")
    try:
        from execution_safety.guardian_bridge import guardian_ok
        ok, det = guardian_ok()
        print(f" GUARDIAN {'ALLOW' if ok else 'BLOCK'} — {det.get('reason', 'evaluated live')}")
    except Exception as e:
        print(f" GUARDIAN unavailable: {e}")
    tg = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    print(f" TELEGRAM {'configured' if tg else 'not configured'}")
    print(f" LOG: {INTEL_LOG}")
    print("=" * 74)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="EURUSD,XAUUSD,NAS100")
    a = ap.parse_args()
    render([s.strip() for s in a.symbols.split(",") if s.strip()])
