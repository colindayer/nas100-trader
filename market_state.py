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
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

LONDON = "Europe/London"
TFS = {"D1": "TIMEFRAME_D1", "H4": "TIMEFRAME_H4", "H1": "TIMEFRAME_H1",
       "M15": "TIMEFRAME_M15", "M5": "TIMEFRAME_M5", "M1": "TIMEFRAME_M1"}
# bar duration per timeframe -- needed to know when a bar actually CLOSED
DUR = {"D1": "1D", "H4": "4h", "H1": "1h", "M15": "15min", "M5": "5min", "M1": "1min"}


_OFFSET_CACHE = {}

# ==================================================================== clock safety (TASK-0005)
# THE DEFECT THIS REPLACES. broker_utc_offset() computed `tick.time - host_now` and rounded it
# to hours. That is a TIMEZONE only while the tick is CURRENT. The moment the feed freezes it
# measures TIMEZONE MINUS STALENESS, and to_london() then subtracts the same value back out, so
# the staleness cancels itself and an arbitrarily old tick yields a current-looking clock.
#
# Measured on the VPS 2026-08-15: freshest tick 2026-08-14 23:54:59, host 12:56:34 UTC,
# offset -13h, desk_now 2026-08-15 13:54:59 London -- from 14-hour-old data. All three guards
# passed: fresh_m1_data compared a stale bar against a stale tick (52s apart), the +/-14h
# sanity band contained -13h, and the leftover 5.9 min was printed as a host NTP warning.
#
# THE RULE. A potentially stale market timestamp may never both establish its own timezone
# interpretation and prove its own freshness. The trusted offset is an INPUT to the freshness
# test and can never be an OUTPUT of it.
CLOCK_STATE_PATH = Path(__file__).resolve().parent / "data" / "logs" / "clock_state.json"
CLOCK_SCHEMA = 1

HOST_DRIFT_TOLERANCE_S       = 300
FEED_LATENCY_ALLOWANCE_S     = 60
FEED_MAX_AGE_S               = 360
FEED_MAX_FUTURE_S            = 60      # a tick may be OLD; it may never be from the FUTURE
FEED_NO_ADVANCE_S            = 120     # ELAPSED host time is trustworthy when ABSOLUTE is not
BOOTSTRAP_MIN_OBSERVATIONS   = 3
BOOTSTRAP_MIN_SPAN_S         = 120
TRUSTED_OFFSET_MAX_AGE_S     = 86400
OFFSET_MIN_CHANGE_INTERVAL_S = 3600
EXPECTED_OFFSETS_H           = (2, 3)  # FTMO-Demo and Pepperstone-Demo are both EET/EEST

# Freshness is measured against host UTC, so a host wrong by more than the tolerance would make
# a LIVE feed fail the absolute test. There is no independent clock source on this host, so the
# two constants must be provably compatible or the states contradict each other.
assert HOST_DRIFT_TOLERANCE_S + FEED_LATENCY_ALLOWANCE_S <= FEED_MAX_AGE_S

CLOCK_STATE_CORRUPT          = "CLOCK_STATE_CORRUPT"
BOOTSTRAPPING                = "BOOTSTRAPPING"
FEED_FRESH                   = "FEED_FRESH"
FEED_STALE                   = "FEED_STALE"
OFFSET_REVALIDATION_REQUIRED = "OFFSET_REVALIDATION_REQUIRED"
HOST_CLOCK_UNTRUSTED         = "HOST_CLOCK_UNTRUSTED"


def _blank_clock_state() -> dict:
    return {"schema_version": CLOCK_SCHEMA, "trusted_offset_h": None, "offset_at": None,
            "last_ts": None, "last_seen": None, "obs": [], "state": None,
            "offset_changed_at": None}


def _load_clock_state(path):
    """Returns (state, error). A corrupt file is NEVER repaired into a permissive value."""
    p = Path(path)
    if not p.exists():
        return None, "missing"
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, "corrupt"
    if not isinstance(st, dict) or st.get("schema_version") != CLOCK_SCHEMA:
        return None, "corrupt"
    types = (("trusted_offset_h", (int, type(None))), ("offset_at", (float, int, type(None))),
             ("last_ts", (int, float, type(None))), ("last_seen", (float, int, type(None))),
             ("obs", list), ("state", (str, type(None))),
             ("offset_changed_at", (float, int, type(None))))
    for key, allowed in types:
        if key not in st or not isinstance(st[key], allowed):
            return None, "corrupt"
    if st["trusted_offset_h"] is not None and st["trusted_offset_h"] not in EXPECTED_OFFSETS_H:
        return None, "corrupt"          # an impossible persisted offset is corruption
    return st, None


def _save_clock_state(path, st) -> None:
    """Atomic. os.replace is atomic on Windows and POSIX alike, so a crash mid-write leaves
    either the old valid state or the new one, never a truncated file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(st, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(p))


def _advancement_proved(obs) -> bool:
    """3+ STRICTLY increasing market timestamps spanning >= BOOTSTRAP_MIN_SPAN_S of host time.
    This is the only timezone-free proof that a feed is alive: it uses DIFFERENCES only, so it
    is immune to both the broker offset and to absolute host error."""
    if len(obs) < BOOTSTRAP_MIN_OBSERVATIONS:
        return False
    w = obs[-BOOTSTRAP_MIN_OBSERVATIONS:]
    if any(w[i + 1][0] <= w[i][0] for i in range(len(w) - 1)):
        return False
    return (w[-1][1] - w[0][1]) >= BOOTSTRAP_MIN_SPAN_S


def market_timestamps(mt5) -> dict:
    """Raw broker tick epoch per CLOCK_SYMBOL. None where unavailable."""
    out = {}
    for sym in CLOCK_SYMBOLS:
        try:
            if not mt5.symbol_select(sym, True):
                out[sym] = None
                continue
            t = mt5.symbol_info_tick(sym)
            out[sym] = int(t.time) if (t and t.time) else None
        except Exception:
            out[sym] = None
    return out


def clock_state(mt5, host_now=None, path=None) -> dict:
    """The ONE clock/freshness verdict for a cycle. Exactly one state holds.

    Order is the fail-closed proof: staleness is decided before any offset question, so a
    frozen feed can never be re-interpreted as a timezone change.
    """
    from datetime import datetime as _dt, timezone as _tz
    path = CLOCK_STATE_PATH if path is None else path
    host_now = float(_dt.now(_tz.utc).timestamp()) if host_now is None else float(host_now)

    st, err = _load_clock_state(path)
    if err == "corrupt":
        try:
            os.replace(str(path), f"{path}.corrupt.{int(host_now)}")
        except Exception:
            pass
        _save_clock_state(path, _blank_clock_state())
        return {"state": CLOCK_STATE_CORRUPT, "entries": False, "offset_h": None,
                "reason": "clock state unreadable; preserved aside, bootstrap required"}
    if st is None:
        st = _blank_clock_state()
        _save_clock_state(path, st)

    stamps = market_timestamps(mt5)
    live = [v for v in stamps.values() if v]
    if not live:
        if st.get("last_seen") is None:
            st["last_seen"] = host_now
        _save_clock_state(path, st)
        return {"state": FEED_STALE, "entries": False, "offset_h": st.get("trusted_offset_h"),
                "reason": "no tick available from any CLOCK_SYMBOL", "stamps": stamps}
    market_ts = max(live)

    prev_ts, prev_seen = st.get("last_ts"), st.get("last_seen")
    advanced = prev_ts is None or market_ts > prev_ts
    backward = prev_ts is not None and market_ts < prev_ts
    elapsed = 0.0 if prev_seen is None else host_now - prev_seen
    # FROZEN and BACKWARD are different observations and must not collapse:
    #   market_ts == last_ts -> the feed stopped        -> FEED_STALE
    #   market_ts <  last_ts -> the timeline moved      -> OFFSET_REVALIDATION_REQUIRED
    stalled = (not advanced) and (not backward) and elapsed > FEED_NO_ADVANCE_S
    if advanced or backward:
        st["last_ts"], st["last_seen"] = market_ts, host_now

    def enter(state):
        """The proof window belongs to ONE state. Without this a pre-freeze window let a FROZEN
        feed satisfy the advancement proof and adopt an offset -- the simulation caught it."""
        if st.get("state") != state:
            st["state"], st["obs"] = state, []
        st["obs"] = (st["obs"] + [[market_ts, host_now]])[-8:]

    def out(state, reason, entries=False, **kw):
        _save_clock_state(path, st)
        return {"state": state, "entries": entries, "reason": reason,
                "offset_h": st.get("trusted_offset_h"), "stamps": stamps,
                "market_ts": market_ts, **kw}

    trusted = st.get("trusted_offset_h")
    oat = st.get("offset_at")
    expired = trusted is not None and (oat is None or host_now - float(oat) > TRUSTED_OFFSET_MAX_AGE_S)

    # ---- no usable trusted offset: BOOTSTRAPPING, blocked, advancement proof first.
    # The circle is broken because liveness is proved by ADVANCEMENT ACROSS TIME while the
    # offset is derived from a SINGLE ABSOLUTE DIFFERENCE -- two different measurements.
    if trusted is None or expired:
        if expired:
            st["trusted_offset_h"] = st["offset_at"] = None
        enter(BOOTSTRAPPING)
        if not _advancement_proved(st["obs"]):
            return out(BOOTSTRAPPING, "awaiting advancement proof")
        cand = int(round((market_ts - host_now) / 3600.0))
        if cand not in EXPECTED_OFFSETS_H:
            return out(BOOTSTRAPPING, f"candidate {cand:+d}h not in {EXPECTED_OFFSETS_H}")
        resid = (market_ts - host_now) - cand * 3600.0
        if abs(resid) > HOST_DRIFT_TOLERANCE_S:      # sub-hour part: host drift, not timezone
            return out(HOST_CLOCK_UNTRUSTED,
                       f"residual {resid:+.0f}s exceeds {HOST_DRIFT_TOLERANCE_S}s", resid=resid)
        st["trusted_offset_h"], st["offset_at"] = cand, host_now
        st["offset_changed_at"] = host_now
        st["last_ts"], st["last_seen"] = market_ts, host_now
        return out(BOOTSTRAPPING, f"offset {cand:+d}h adopted; re-evaluating next cycle")

    if stalled:
        enter(FEED_STALE)
        return out(FEED_STALE, f"no advancement for {elapsed:.0f}s")

    # HOST BEFORE OFFSET. The sub-hour part of the raw difference is host drift no matter which
    # hour is correct -- this is clock_skew()'s formula -- so it stays small across a legitimate
    # DST step and large under real host error. Testing it first keeps the two diagnostics
    # cleanly separated: a stale feed is a broker/network/terminal problem, an untrusted host is
    # a Windows/NTP problem, and an operator must not be sent to the wrong one. Staleness is
    # already decided above, so this can never mask a dead feed.
    raw = market_ts - host_now
    resid = raw - round(raw / 3600.0) * 3600.0
    if abs(resid) > HOST_DRIFT_TOLERANCE_S:
        enter(HOST_CLOCK_UNTRUSTED)
        return out(HOST_CLOCK_UNTRUSTED,
                   f"host residual {resid:+.0f}s exceeds {HOST_DRIFT_TOLERANCE_S}s", resid=resid)

    age = host_now - (market_ts - trusted * 3600.0)
    if backward or not (-FEED_MAX_FUTURE_S <= age <= FEED_MAX_AGE_S):
        enter(OFFSET_REVALIDATION_REQUIRED)
        if not _advancement_proved(st["obs"]):
            return out(OFFSET_REVALIDATION_REQUIRED,
                       f"age {age:+.0f}s out of band; awaiting advancement proof", age=age)
        cand = int(round((market_ts - host_now) / 3600.0))
        if cand not in EXPECTED_OFFSETS_H:
            return out(OFFSET_REVALIDATION_REQUIRED,
                       f"candidate {cand:+d}h implausible; keeping {trusted:+d}h")
        if cand == trusted:
            return out(HOST_CLOCK_UNTRUSTED,
                       f"offset confirmed {cand:+d}h; residual {resid:+.0f}s is the host",
                       resid=resid)
        if abs(cand - trusted) != 1:
            return out(OFFSET_REVALIDATION_REQUIRED,
                       f"candidate {cand:+d}h is not a 1h step from {trusted:+d}h")
        since = host_now - float(st.get("offset_changed_at") or 0.0)
        if since < OFFSET_MIN_CHANGE_INTERVAL_S:
            return out(OFFSET_REVALIDATION_REQUIRED,
                       f"offset changed {since / 3600:.1f}h ago; minimum interval not met")
        st["trusted_offset_h"], st["offset_at"] = cand, host_now
        st["offset_changed_at"] = host_now
        st["last_ts"], st["last_seen"] = market_ts, host_now
        return out(OFFSET_REVALIDATION_REQUIRED,
                   f"DST {trusted:+d}h -> {cand:+d}h adopted; re-evaluating next cycle")

    enter(FEED_FRESH)
    st["offset_at"] = host_now
    return out(FEED_FRESH, "feed advancing, age in band, host within tolerance",
               entries=True, age=age, resid=resid)


def symbol_feed_fresh(mt5, symbol, host_now=None, path=None) -> tuple:
    """Per-symbol gate for the TRADED instrument. A GLOBAL clock built from the freshest tick
    across five symbols stays FEED_FRESH while one instrument's own feed is frozen, and the bot
    trading it would evaluate stale bars and reach order_send. Global freshness is not enough.
    """
    from datetime import datetime as _dt, timezone as _tz
    host_now = float(_dt.now(_tz.utc).timestamp()) if host_now is None else float(host_now)
    st, err = _load_clock_state(CLOCK_STATE_PATH if path is None else path)
    trusted = None if err else st.get("trusted_offset_h")
    if trusted is None:
        return False, "no trusted offset"
    try:
        t = mt5.symbol_info_tick(symbol)
        ts = int(t.time) if (t and t.time) else None
    except Exception:
        ts = None
    if ts is None:
        return False, f"no tick for {symbol}"
    age = host_now - (ts - trusted * 3600.0)
    if not (-FEED_MAX_FUTURE_S <= age <= FEED_MAX_AGE_S):
        return False, f"{symbol} feed is {age:+.0f}s old"
    return True, f"{symbol} feed {age:+.0f}s"




def broker_utc_offset(mt5, symbol="XAUUSD"):
    """How far the BROKER's clock sits from real UTC.

    MT5 returns bar and tick times in SERVER time, not UTC. Reading them as UTC and then
    converting to London added the London offset on top of the server offset, putting the
    desk 3 hours ahead: a bot whose window says 06:30 London was trading 03:30 London.

    Measured, not hardcoded -- brokers change offset with DST and this must not need a code
    change twice a year.

    TASK-0005: this no longer MEASURES anything. It returns the offset that was established
    earlier, on a feed independently proven live, and persisted. Deriving it from the current
    tick is exactly the defect being repaired -- see clock_state() above. Zero is returned when
    no trusted offset exists, and clock_state() blocks new entries in that condition, so an
    unverified offset can only ever reach diagnostics.

    ROUNDED TO THE HOUR, and the evidence says that is right. Broker offsets are whole hours
    (FTMO is UTC+2/+3 by season). The HOST is the unreliable clock: this VPS drifted -133s ->
    -209s -> -304s across three runs despite NTP, which is normal on a hypervisor guest whose
    host time provider fights w32time.

    So the host is used only to infer WHICH hour, and its drift is then discarded. That makes
    every session window immune to host drift up to +-30 minutes. The earlier 15-minute
    rounding was wrong for the opposite reason -- it kept part of the skew while looking
    precise. The residual is reported by clock_skew() as a host-health signal.
    """
    import pandas as pd
    if "off" in _OFFSET_CACHE:
        return _OFFSET_CACHE["off"]
    st, err = _load_clock_state(CLOCK_STATE_PATH)
    h = None if err else st.get("trusted_offset_h")
    off = pd.Timedelta(hours=h) if h is not None else pd.Timedelta(0)
    _OFFSET_CACHE["off"] = off
    return off


def clock_skew(mt5, symbol="XAUUSD"):
    """How far THIS HOST sits from the broker's whole-hour grid. Purely a host-health signal
    now: the offset is hour-rounded, so this no longer affects any session window. Report it,
    do not act on it."""
    import pandas as pd
    from datetime import datetime, timezone
    try:
        tick = mt5.symbol_info_tick(symbol)
        raw = tick.time - datetime.now(timezone.utc).timestamp()
        return pd.Timedelta(seconds=raw - round(raw / 3600) * 3600)
    except Exception:
        return pd.Timedelta(0)


CLOCK_SYMBOLS = ("XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "US100.cash")


def broker_now_london(mt5, symbol=None):
    """CURRENT time, from the BROKER, using the FRESHEST tick on the whole desk.

    Fixed twice now, so the failure mode is worth stating. Session time first came from
    `m1.index[-1]` -- the newest BAR for one symbol. Replacing that with that symbol's last
    TICK moved the bug without removing it: both go stale the moment that market closes, and
    the desk again showed two clocks in one cycle (EURUSD 23:58, US500 22:49).

    A per-symbol clock is wrong by construction. The desk has ONE time, so take the newest
    tick across several liquid instruments -- at least one is always trading during any
    window a bot owns.
    """
    import pandas as pd
    newest = None
    for s in CLOCK_SYMBOLS:
        try:
            if not mt5.symbol_select(s, True):
                continue
            t = mt5.symbol_info_tick(s)
            if t and t.time and (newest is None or t.time > newest):
                newest = t.time
        except Exception:
            continue
    if newest is None:
        raise RuntimeError("no broker tick available on any clock symbol")
    return (pd.Timestamp(newest, unit="s", tz="UTC")
            - broker_utc_offset(mt5)).tz_convert(LONDON)


def to_london(series_or_epoch, offset):
    """Server epoch -> true UTC -> London. The only correct path for MT5 times."""
    import pandas as pd
    u = pd.to_datetime(series_or_epoch, unit="s", utc=True) - offset
    # NOT hasattr(u,"tz_convert"): a Series HAS that method but it converts the INDEX, so the
    # hasattr check silently took the wrong branch and raised on real data.
    return u.dt.tz_convert(LONDON) if isinstance(u, pd.Series) else u.tz_convert(LONDON)


def _bars(mt5, symbol, tf_name, n, now):
    """Closed bars only, strictly before `now`."""
    import pandas as pd
    tf = getattr(mt5, TFS[tf_name])
    r = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if r is None or not len(r):
        return None
    d = pd.DataFrame(r)
    d.index = to_london(d["time"], broker_utc_offset(mt5, symbol))
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


def _regime(price, sma20, sma50, atr, slope20) -> str:
    """up / down / range / transition. Distinct from 'undetermined': a range must be
    POSITIVELY identified -- price near its own mean and that mean going nowhere."""
    if not (sma20 and atr):
        return "unknown"
    FLAT = 0.0005
    dist = abs(price - sma20) / atr
    flat = slope20 is not None and abs(slope20) < FLAT
    if dist <= 0.5 and flat:
        return "range"
    # A trend needs its MEAN to be moving. Price far above a flat average is a spike or a
    # young recovery, not an established uptrend -- and calling it one would license
    # trend-following into a mean that has not confirmed anything yet.
    if sma50 and price > sma20 > sma50 and (slope20 or 0) > FLAT:
        return "up"
    if sma50 and price < sma20 < sma50 and (slope20 or 0) < -FLAT:
        return "down"
    return "transition"


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
        f"{tag}_swing_structure": ("up" if hh and hl else "down" if lh and ll
                                  else "undetermined"),
        f"{tag}_atr20": tr,
        # A REGIME, not a pattern-match fallback. The old field returned "mixed" whenever the
        # 3-bar detector found nothing, so "ranging" and "no idea" were the same value -- and
        # a gate built on it would have approved a fade 2 ATR above the mean.
        f"{tag}_regime": _regime(price, sma20, sma50, tr,
                                 _slope(c.rolling(20).mean().dropna())),
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
    # mutually exclusive -- the engine emitted TREND_UP and RANGE together, which is not a
    # description of anything and would have justified both a breakout and a fade.
    reg = v.get("d1_regime")
    if reg == "up":
        L.append("TREND_UP")
    elif reg == "down":
        L.append("TREND_DOWN")
    elif reg == "range":
        L.append("RANGE")
    elif reg == "transition":
        L.append("TRANSITION")
    ts = v.get("d1_trend_strength_atr")
    if ts is not None and abs(ts) >= 2.0:
        L.append("EXTENDED")
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
