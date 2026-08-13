"""MARKET STATE ENGINE — one implementation, every bot, every signal.

    py market_state.py --symbol XAUUSD      print the current vector (needs MT5)

TIMESTAMP SAFETY IS THE WHOLE POINT
  Every series is truncated to bars that had CLOSED at the signal timestamp. The forming bar
  is dropped everywhere. A state vector containing the bar the signal fired in would leak the
  breakout's own outcome into the features meant to explain it -- and the leak only shows up
  months later as a shadow variant that "works" and then dies live.

  Nothing here revises. Nothing here looks forward. If a value cannot be computed from closed
  bars it is None, never a guess.

COMPONENTS, NOT A VERDICT
  This module does not decide anything. It returns numbers and descriptive labels. Whether
  trend alignment or DXY agreement actually pays is a question for the Brain once live trades
  carry these labels -- collapsing them into one score here would destroy the evidence needed
  to answer it.
"""
from __future__ import annotations

import argparse
import math
from datetime import datetime

LONDON = "Europe/London"
TFS = {"D1": "TIMEFRAME_D1", "H4": "TIMEFRAME_H4", "H1": "TIMEFRAME_H1",
       "M15": "TIMEFRAME_M15", "M5": "TIMEFRAME_M5", "M1": "TIMEFRAME_M1"}
# bar duration per timeframe -- needed to know when a bar actually CLOSED
DUR = {"D1": "1D", "H4": "4h", "H1": "1h", "M15": "15min", "M5": "5min", "M1": "1min"}


def _bars(mt5, symbol, tf_name, n, now):
    """Closed bars only, strictly before `now`."""
    import pandas as pd
    tf = getattr(mt5, TFS[tf_name])
    r = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if r is None or not len(r):
        return None
    d = pd.DataFrame(r)
    d.index = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert(LONDON)
    # A bar is usable only once it has CLOSED. Filtering on the bar's OPEN timestamp keeps
    # the bar the signal fired inside -- whose high/low already contain the breakout being
    # measured. That is lookahead even though no future data is involved.
    d = d[d.index + pd.Timedelta(DUR[tf_name]) <= now]
    return d if len(d) else None


def _slope(series, n=5):
    """Normalised slope of the last n points, in units of the series' own level."""
    if series is None or len(series) < n + 1:
        return None
    a, b = float(series.iloc[-n - 1]), float(series.iloc[-1])
    return (b - a) / abs(a) if a else None


def _swing(d, lookback=40, kind="high"):
    """Most recent fractal swing: a bar higher/lower than its 2 neighbours each side."""
    if d is None or len(d) < 10:
        return None
    w = d.tail(lookback)
    h, l = w["high"].to_numpy(), w["low"].to_numpy()
    for i in range(len(w) - 3, 1, -1):
        if kind == "high" and h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1]:
            return float(h[i])
        if kind == "low" and l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1]:
            return float(l[i])
    return None


def _tf_block(d, price, tag) -> dict:
    """Trend components for one timeframe. Stored separately, never collapsed."""
    out = {f"{tag}_bars": 0 if d is None else len(d)}
    if d is None or len(d) < 25:
        return out
    c = d["close"]
    sma20 = float(c.tail(20).mean())
    sma50 = float(c.tail(50).mean()) if len(c) >= 50 else None
    sma200 = float(c.tail(200).mean()) if len(c) >= 200 else None
    tr = float((d["high"] - d["low"]).tail(20).mean()) or None

    hh = hl = lh = ll = None
    if len(d) >= 6:
        h, l = d["high"], d["low"]
        hh = bool(h.iloc[-1] > h.iloc[-3] > h.iloc[-5])
        hl = bool(l.iloc[-1] > l.iloc[-3] > l.iloc[-5])
        lh = bool(h.iloc[-1] < h.iloc[-3] < h.iloc[-5])
        ll = bool(l.iloc[-1] < l.iloc[-3] < l.iloc[-5])

    out.update({
        f"{tag}_price_vs_sma20": (price - sma20) / sma20 if sma20 else None,
        f"{tag}_price_vs_sma50": (price - sma50) / sma50 if sma50 else None,
        f"{tag}_price_vs_sma200": (price - sma200) / sma200 if sma200 else None,
        f"{tag}_above_sma20": price > sma20 if sma20 else None,
        f"{tag}_above_sma50": price > sma50 if sma50 else None,
        f"{tag}_above_sma200": price > sma200 if sma200 else None,
        f"{tag}_sma20_slope": _slope(c.rolling(20).mean().dropna()),
        f"{tag}_sma50_slope": _slope(c.rolling(50).mean().dropna()) if len(c) >= 55 else None,
        f"{tag}_hh": hh, f"{tag}_hl": hl, f"{tag}_lh": lh, f"{tag}_ll": ll,
        f"{tag}_structure": ("up" if hh and hl else "down" if lh and ll else "mixed"),
        f"{tag}_atr20": tr,
        # trend strength in ATR units: how far price sits from its own mean, scaled by noise
        f"{tag}_trend_strength_atr": (price - sma20) / tr if (tr and sma20) else None,
    })
    return out


def _momentum(d1, h1, price) -> dict:
    out = {}
    if h1 is not None and len(h1) > 5:
        c = h1["close"]
        for k, bars in (("1h", 1), ("4h", 4)):
            if len(c) > bars:
                out[f"ret_{k}"] = float(price / c.iloc[-bars] - 1)
    if d1 is not None and len(d1) > 6:
        c = d1["close"]
        for k, bars in (("1d", 1), ("3d", 3), ("5d", 5)):
            if len(c) > bars:
                out[f"ret_{k}"] = float(price / c.iloc[-bars] - 1)
        tr = float((d1["high"] - d1["low"]).tail(20).mean())
        if tr:
            out["mom_1d_atr"] = (price - float(d1["close"].iloc[-1])) / tr
            out["roc_5d_atr"] = ((price - float(d1["close"].iloc[-5])) / tr
                                 if len(c) > 5 else None)
    return out


def _volatility(d1, m1, now, session_start) -> dict:
    out = {}
    if d1 is not None and len(d1) >= 20:
        rng = (d1["high"] - d1["low"])
        atr20 = float(rng.tail(20).mean())
        out["atr20_d1"] = atr20
        hist = rng.tail(100)
        out["atr_percentile"] = float((hist < atr20).mean()) if len(hist) > 20 else None
        recent, older = float(rng.tail(5).mean()), float(rng.tail(20).mean())
        out["vol_expansion"] = recent / older if older else None
        out["vol_regime"] = ("expanding" if out["vol_expansion"] and out["vol_expansion"] > 1.2
                             else "contracting" if out["vol_expansion"]
                             and out["vol_expansion"] < 0.8 else "stable")
    if m1 is not None and len(m1) > 30:
        r = m1["close"].pct_change().dropna()
        out["realized_vol_intraday"] = float(r.std() * math.sqrt(1440)) if len(r) > 10 else None
        out["realized_vol_60m"] = (float(r.tail(60).std() * math.sqrt(1440))
                                   if len(r) >= 60 else None)
        if session_start is not None:
            s = m1[m1.index >= session_start]
            if len(s):
                sr = float(s["high"].max() - s["low"].min())
                out["session_range"] = sr
                out["session_range_atr"] = (sr / out["atr20_d1"]
                                            if out.get("atr20_d1") else None)
    return out


def _levels(d1, h1, h4, m1, price, now, atr) -> dict:
    """Distances to reference levels, in price AND in ATR units."""
    import pandas as pd
    out, lv = {}, {}
    if d1 is not None and len(d1) >= 2:
        prev = d1.iloc[-1]
        lv.update({"prev_day_high": float(prev["high"]), "prev_day_low": float(prev["low"]),
                   "prev_day_close": float(prev["close"])})
        # Multiple horizons. A 20-day window cannot see a 3-month peak: NAS100's June high
        # sat ~400pt above an August fade and was invisible to every lookback here, so the
        # desk could not tell "faded into overhead structure" from "faded into open air".
        for n in (20, 60, 120, 250):
            if len(d1) >= n:
                lv[f"high_{n}d"] = float(d1["high"].tail(n).max())
                lv[f"low_{n}d"] = float(d1["low"].tail(n).min())
    if m1 is not None and len(m1):
        day = now.normalize()
        today = m1[m1.index >= day]
        if len(today):
            lv["daily_open"] = float(today["open"].iloc[0])
        asia = m1[(m1.index >= day) & (m1.index < day + pd.Timedelta(hours=7))]
        if len(asia):
            lv["asia_high"] = float(asia["high"].max())
            lv["asia_low"] = float(asia["low"].min())
        lon = m1[(m1.index >= day + pd.Timedelta(hours=8)) & (m1.index < now)]
        if len(lon):
            lv["london_high"] = float(lon["high"].max())
            lv["london_low"] = float(lon["low"].min())
        wk = m1[m1.index >= day - pd.Timedelta(days=int(now.dayofweek))]
        if len(wk):
            lv["weekly_open"] = float(wk["open"].iloc[0])
    for tag, d in (("h1", h1), ("h4", h4)):
        hi, lo = _swing(d, kind="high"), _swing(d, kind="low")
        if hi: lv[f"{tag}_swing_high"] = hi
        if lo: lv[f"{tag}_swing_low"] = lo

    for k, v in lv.items():
        out[f"lvl_{k}"] = v
        out[f"dist_{k}"] = price - v
        out[f"dist_{k}_atr"] = (price - v) / atr if atr else None

    # nearest higher-timeframe level ABOVE and BELOW -- how much room the trade has
    above = [(v - price) for v in lv.values() if v > price]
    below = [(price - v) for v in lv.values() if v < price]
    out["room_above"] = min(above) if above else None
    out["room_below"] = min(below) if below else None
    # how far price sits inside its own multi-month range: 1.0 = at the 120d high
    hi120, lo120 = lv.get("high_120d"), lv.get("low_120d")
    if hi120 and lo120 and hi120 > lo120:
        out["range_position_120d"] = (price - lo120) / (hi120 - lo120)
    out["room_above_atr"] = (min(above) / atr) if (above and atr) else None
    out["room_below_atr"] = (min(below) / atr) if (below and atr) else None
    return out


def breakout_quality(m1, level, side, session_start, now, atr, spread) -> dict:
    """Descriptive quality of THIS break. Diagnostic only -- no bot rejects on it yet."""
    out = {}
    if m1 is None or not len(m1):
        return out
    s = m1[(m1.index >= session_start) & (m1.index < now)]
    if not len(s):
        return out
    last = s.iloc[-1]
    body = abs(float(last["close"] - last["open"]))
    rng = float(last["high"] - last["low"])
    out.update({
        "bq_break_candle_size": rng,
        "bq_break_candle_atr": rng / atr if atr else None,
        "bq_body_ratio": body / rng if rng else None,
        "bq_wick_ratio": 1 - (body / rng) if rng else None,
        "bq_close_outside": bool(
            (float(last["close"]) > level) if side > 0 else (float(last["close"]) < level)),
        "bq_dist_through_level": abs(float(last["close"]) - level),
        "bq_dist_through_level_atr": abs(float(last["close"]) - level) / atr if atr else None,
        "bq_spread_at_break": spread,
        "bq_spread_over_atr": spread / atr if atr else None,
    })
    touch = ((s["high"] >= level) if side > 0 else (s["low"] <= level))
    out["bq_prior_tests"] = int(touch.sum())
    out["bq_first_break"] = bool(touch.sum() <= 1)
    out["bq_break_type"] = "clean" if out["bq_first_break"] else "repeated"
    if len(s) > 15:
        pre = s.iloc[-15:-1]
        out["bq_momentum_before"] = float(pre["close"].iloc[-1] / pre["close"].iloc[0] - 1)
    return out


def reversion_quality(m1, vwap, sigma, price, session_start, now, atr) -> dict:
    out = {}
    if m1 is None or not len(m1) or not sigma:
        return out
    s = m1[(m1.index >= session_start) & (m1.index < now)]
    out.update({
        "rq_dist_vwap": price - vwap,
        "rq_dist_vwap_atr": (price - vwap) / atr if atr else None,
        "rq_zscore": (price - vwap) / sigma,
    })
    if len(s) > 20:
        rng = float(s["high"].max() - s["low"].min())
        out["rq_session_range_atr"] = rng / atr if atr else None
        c = s["close"]
        out["rq_range_percentile"] = float((c < price).mean())
    return out


def classify(v: dict) -> list:
    """Descriptive labels. Multiple may hold at once. NOT filters -- the Brain measures
    whether any of them predicts expectancy once live trades carry them."""
    L = []
    st = v.get("d1_structure")
    if v.get("d1_above_sma20") and v.get("d1_above_sma50"):
        L.append("TREND_UP")
    elif v.get("d1_above_sma20") is False and v.get("d1_above_sma50") is False:
        L.append("TREND_DOWN")
    if st == "mixed":
        L.append("RANGE")
    p = v.get("atr_percentile")
    if p is not None:
        L.append("HIGH_VOL" if p > 0.75 else "LOW_VOL" if p < 0.25 else "MID_VOL")
    vr = v.get("vol_regime")
    if vr == "expanding":
        L.append("VOL_EXPANDING")
    elif vr == "contracting":
        L.append("VOL_CONTRACTING")
    if v.get("bq_break_type") == "clean":
        L.append("BREAKOUT_CLEAN")
    elif v.get("bq_break_type") == "repeated":
        L.append("BREAKOUT_REPEATED")
    ra, rb = v.get("room_above_atr"), v.get("room_below_atr")
    if ra is not None and ra < 0.5:
        L.append("NEAR_HTF_RESISTANCE")
    if rb is not None and rb < 0.5:
        L.append("NEAR_HTF_SUPPORT")
    return L


def compute(mt5, symbol, now_london, price, spread, session_start=None,
            level=None, side=None, vwap=None, sigma=None) -> dict:
    """The full vector. Every value derived from bars closed before `now_london`."""
    v = {"ms_symbol": symbol, "ms_timestamp": now_london.isoformat(), "spread": spread}
    try:
        d1 = _bars(mt5, symbol, "D1", 260, now_london)
        h4 = _bars(mt5, symbol, "H4", 260, now_london)
        h1 = _bars(mt5, symbol, "H1", 300, now_london)
        m15 = _bars(mt5, symbol, "M15", 300, now_london)
        m1 = _bars(mt5, symbol, "M1", 1400, now_london)
    except Exception as e:
        return {**v, "ms_error": str(e)}

    for tag, d in (("d1", d1), ("h4", h4), ("h1", h1), ("m15", m15)):
        v.update(_tf_block(d, price, tag))
    v.update(_momentum(d1, h1, price))
    v.update(_volatility(d1, m1, now_london, session_start))

    atr = v.get("atr20_d1")
    v.update(_levels(d1, h1, h4, m1, price, now_london, atr))

    v["spread_over_atr"] = spread / atr if (atr and spread) else None
    if session_start is not None:
        v["minutes_since_session_open"] = int(
            (now_london - session_start).total_seconds() // 60)
    if m1 is not None and len(m1) > 60:
        exc = (m1["high"] - m1["low"]).tail(60)
        v["m1_excursion_median_60"] = float(exc.median())
        v["m1_excursion_p90_60"] = float(exc.quantile(0.9))

    if level is not None and side is not None:
        v.update(breakout_quality(m1, level, side, session_start, now_london, atr, spread))
    if vwap is not None:
        v.update(reversion_quality(m1, vwap, sigma, price, session_start, now_london, atr))

    v["ms_labels"] = classify(v)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    a = ap.parse_args()
    import MetaTrader5 as mt5, pandas as pd
    if not mt5.initialize():
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    t = mt5.symbol_info_tick(a.symbol)
    now = pd.Timestamp.now(tz=LONDON)
    v = compute(mt5, a.symbol, now, t.ask, t.ask - t.bid,
                session_start=now.normalize() + pd.Timedelta(hours=8))
    for k in sorted(v):
        print(f"  {k:<34}{v[k]}")
    print(f"\n  {len(v)} fields   labels: {v.get('ms_labels')}")
    mt5.shutdown()


if __name__ == "__main__":
    main()
