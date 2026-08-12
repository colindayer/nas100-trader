"""MACRO CONTEXT — cross-asset state at the signal timestamp. Measured, never narrated.

Only things the desk can read off a price feed. No commentary, no "the market expects".

CALENDAR: the MT5 Python API exposes no economic calendar, and buying a feed needs approval.
Every event field is therefore NULL, explicitly. A null is a missing measurement; a guessed
event time would be fabricated data, which is worse than not having it.
"""
from __future__ import annotations

PROXIES = {"dxy": "USDX.cash", "gold": "XAUUSD", "nas": "US100.cash",
           "spx": "US500.cash", "eur": "EURUSD"}

# what each traded symbol actually wants to know about
RELEVANT = {
    "XAUUSD": ["dxy", "nas", "spx", "eur"],
    "US100.cash": ["dxy", "gold", "spx"],
    "US500.cash": ["dxy", "gold", "nas"],
    "EURUSD": ["dxy", "gold", "spx"],
}


def _ret(mt5, symbol, now, bars=1, tf="TIMEFRAME_D1"):
    """Return over `bars` closed bars. None if the symbol is unavailable here."""
    import pandas as pd
    try:
        if not mt5.symbol_select(symbol, True):
            return None, None
        r = mt5.copy_rates_from_pos(symbol, getattr(mt5, tf), 0, 60)
        if r is None or len(r) < bars + 25:
            return None, None
        d = pd.DataFrame(r)
        d.index = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("Europe/London")
        d = d[d.index < now]                      # closed bars only
        if len(d) < bars + 25:
            return None, None
        c = d["close"]
        ret = float(c.iloc[-1] / c.iloc[-1 - bars] - 1)
        sma20 = float(c.tail(20).mean())
        return ret, ("up" if float(c.iloc[-1]) > sma20 else "down")
    except Exception:
        return None, None


def compute(mt5, symbol, now_london) -> dict:
    """Cross-asset context for `symbol`. Absent instruments stay None, never zero --
    a zero return would read as 'flat' and quietly become evidence."""
    out = {"macro_symbol": symbol}
    wanted = RELEVANT.get(symbol, ["dxy"])
    got = {}
    for key in wanted:
        sym = PROXIES.get(key)
        if not sym or sym == symbol:
            continue
        r1, trend = _ret(mt5, sym, now_london, 1)
        r5, _ = _ret(mt5, sym, now_london, 5)
        out[f"macro_{key}_ret_1d"] = r1
        out[f"macro_{key}_ret_5d"] = r5
        out[f"macro_{key}_trend"] = trend
        if r1 is not None:
            got[key] = r1

    if "dxy" in got:
        out["macro_usd"] = "USD_STRONG" if got["dxy"] > 0 else "USD_WEAK"
    equities = [got[k] for k in ("nas", "spx") if k in got]
    if equities:
        avg = sum(equities) / len(equities)
        out["macro_risk"] = "RISK_ON" if avg > 0 else "RISK_OFF"
        out["macro_equity_ret_1d"] = avg

    # divergences: the pairs that historically matter for these instruments
    if symbol == "XAUUSD":
        if "dxy" in got:
            own, _ = _ret(mt5, symbol, now_london, 1)
            if own is not None:
                out["macro_gold_vs_dollar_divergence"] = (
                    "aligned" if (own > 0) != (got["dxy"] > 0) else "divergent")
        if equities:
            own, _ = _ret(mt5, symbol, now_london, 1)
            if own is not None:
                out["macro_gold_vs_equity"] = (
                    "same_direction" if (own > 0) == (avg > 0) else "opposite")

    # calendar: unavailable, and explicitly so
    out.update({"macro_minutes_to_event": None, "macro_minutes_since_event": None,
                "macro_event_category": None,
                "macro_calendar_status": "UNAVAILABLE — no verified feed; "
                                         "MT5 Python API exposes none"})
    labels = [v for k, v in out.items()
              if k in ("macro_usd", "macro_risk") and isinstance(v, str)]
    out["macro_labels"] = labels
    return out
