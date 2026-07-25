"""reaction_recorder.py -- PHASE 701. Records what markets ACTUALLY did after each economic release.
This builds the only dataset that can later justify a news strategy. It never trades and never
predicts; it observes and stores.

Run it on a schedule (e.g. every 15 min):
    py -m market_intel.reaction_recorder --symbols EURUSD,XAUUSD,NAS100

For every event whose `actual` has appeared, it snapshots price at T+5m/15m/30m/1h/4h relative to
the release timestamp and appends an immutable observation.
"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timedelta, timezone

STORE = "registry/news_reactions.jsonl"
SEEN = "registry/news_reactions_seen.json"
HORIZONS_MIN = [5, 15, 30, 60, 240]


def _seen() -> dict:
    return json.load(open(SEEN)) if os.path.exists(SEEN) else {}


def _mark(key, payload):
    d = _seen(); d[key] = payload
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    json.dump(d, open(SEEN, "w"), indent=1)


def _bars(symbol, minutes_back=900):
    import MetaTrader5 as mt5, pandas as pd
    r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, minutes_back // 5)
    if r is None or not len(r):
        return None
    d = pd.DataFrame(r); d["time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    return d.set_index("time")[["open", "high", "low", "close"]]


def _price_at(df, ts):
    """Close of the last bar at or before ts, else None."""
    try:
        sub = df.loc[:ts]
        return float(sub["close"].iloc[-1]) if len(sub) else None
    except Exception:
        return None


def record_all(symbols, max_age_hours=24) -> list:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    from . import calendar_feed as cal
    events = cal.load()
    now = datetime.now(timezone.utc)
    seen = _seen()
    written = []
    for e in events:
        if e.actual is None or e.forecast is None:      # need a real surprise
            continue
        try:
            t = datetime.fromisoformat(str(e.scheduled).replace("Z", "+00:00"))
            if t.tzinfo is None: t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if not (timedelta(0) <= now - t <= timedelta(hours=max_age_hours)):
            continue                                     # too old or not yet released
        for sym in symbols:
            key = f"{e.event_id}|{sym}"
            if key in seen:
                continue
            df = _bars(sym)
            if df is None:
                continue
            base = _price_at(df, t)
            if not base:
                continue
            moves = {}
            complete = True
            for m in HORIZONS_MIN:
                p = _price_at(df, t + timedelta(minutes=m))
                if p is None or (now - t) < timedelta(minutes=m):
                    complete = False; continue
                moves[f"t+{m}m"] = round(p / base - 1, 6)
            if not moves:
                continue
            obs = {"recorded_at": now.isoformat(), "event_id": e.event_id, "event": e.name,
                   "currency": e.currency, "impact": e.impact, "scheduled": e.scheduled,
                   "previous": e.previous, "forecast": e.forecast, "actual": e.actual,
                   "surprise": e.surprise(), "surprise_pct": e.surprise_pct(),
                   "symbol": sym, "price_at_release": base, "moves": moves, "complete": complete}
            os.makedirs(os.path.dirname(STORE), exist_ok=True)
            with open(STORE, "a") as f:
                f.write(json.dumps(obs) + "\n")
            written.append(obs)
            if complete:
                _mark(key, {"scheduled": e.scheduled, "symbol": sym})
    return written


def summary() -> dict:
    if not os.path.exists(STORE):
        return {"observations": 0}
    rows = [json.loads(l) for l in open(STORE) if l.strip()]
    hi = [r for r in rows if r.get("impact") == "high"]
    return {"observations": len(rows), "high_impact": len(hi),
            "distinct_events": len({r["event"] for r in rows}),
            "symbols": sorted({r["symbol"] for r in rows}),
            "note": "A news strategy needs hundreds of high-impact observations. "
                    "Keep this running; do not trade on a handful."}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="EURUSD,XAUUSD,NAS100")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        print(json.dumps(summary(), indent=1))
    else:
        w = record_all([s.strip() for s in a.symbols.split(",") if s.strip()])
        print(f"recorded {len(w)} new observations")
        for o in w[:8]:
            print(f"  {o['currency']} {o['event'][:28]:30s} surprise={o['surprise']} "
                  f"{o['symbol']} moves={o['moves']}")
        print(json.dumps(summary(), indent=1))
