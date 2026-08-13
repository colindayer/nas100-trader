"""SHADOW VARIANTS — hypothesis testing that costs nothing and risks nothing.

A shadow is a PREDICATE over the market state, evaluated at the live signal's timestamp and
recorded beside it. It never sends an order.

WHY FILTERS AND NOT FORKED BOTS
  A filter shadow takes the parent's exact entry, stop and target, so when it says "take this
  one" its outcome IS the parent's realised outcome -- no simulation, no fill assumptions, no
  walk-forward model to be wrong about. Shadow expectancy is then a real subset of real
  trades. A shadow that changed the stop would need its own fill model, and a fill model is
  precisely the thing that has been wrong every time it has been assumed.

WHAT THIS CANNOT SEE
  Only trades the LIVE bot actually took. A shadow can prove "you should have skipped these",
  never "you should also have taken those". Add the mirror-image variant to the live desk if
  the second question matters.

Predicates return True (would take), False (would skip), or None (cannot evaluate -- data
missing). None is NOT False: an unevaluable variant must not look selective.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "data" / "challenge" / "shadows.jsonl"


class Shadow:
    def __init__(self, name, rationale, fn):
        self.name, self.rationale, self.fn = name, rationale, fn

    def evaluate(self, st: dict):
        try:
            return self.fn(st)
        except Exception:
            return None


def _trend_align(st):
    """Take the break only when the daily structure agrees with its direction."""
    up = st.get("d1_above_sma20")
    side = st.get("_side")
    if up is None or side is None:
        return None
    return bool((side > 0 and up) or (side < 0 and not up))


def _htf_room(st):
    """Take it only with at least 0.5 ATR of clear air to the next HTF level."""
    side = st.get("_side")
    room = st.get("room_above_atr") if (side or 0) > 0 else st.get("room_below_atr")
    return None if room is None else bool(room >= 0.5)


def _vol_expansion(st):
    """Breakouts should want expanding volatility; this asks whether that is true here."""
    v = st.get("vol_expansion")
    return None if v is None else bool(v >= 1.0)


def _clean_break(st):
    """First test of the level only -- the repeated-break hypothesis, measured."""
    t = st.get("bq_break_type")
    return None if t is None else (t == "clean")


def _usd_align(st):
    """Gold specific: take longs when the dollar is soft, shorts when firm."""
    usd, side = st.get("macro_usd"), st.get("_side")
    if usd is None or side is None:
        return None
    return bool((side > 0 and usd == "USD_WEAK") or (side < 0 and usd == "USD_STRONG"))


def _wide_stop(st):
    """Would a stop of >=0.25 ATR have survived? Records the geometry question without
    changing any live stop."""
    sl, atr = st.get("_sl_dist"), st.get("atr20_d1")
    if not sl or not atr:
        return None
    return bool(sl >= 0.25 * atr)


def _not_extended(st):
    """Skip breaks that fire when price is already far from its own mean."""
    ts = st.get("d1_trend_strength_atr")
    return None if ts is None else bool(abs(ts) <= 2.0)


COMMON = [
    Shadow("v2_trend_align", "D1 structure agrees with the trade direction", _trend_align),
    Shadow("v3_htf_room", ">=0.5 ATR of clear air to the next HTF level", _htf_room),
    Shadow("v4_vol_expansion", "daily range expanding, not contracting", _vol_expansion),
    Shadow("v5_clean_break", "first test of the level, not a repeated break", _clean_break),
    Shadow("v6_wide_stop", "stop was at least 0.25 ATR", _wide_stop),
    Shadow("v7_not_extended", "price within 2 ATR of its own D1 mean", _not_extended),
]
GOLD = COMMON + [Shadow("v8_usd_align", "dollar direction agrees", _usd_align)]

REGISTRY = {
    "BOT_A_gold_0630_breakout": GOLD,
    "BOT_D_gold_ny_breakout": GOLD,
    "BOT_B_nas100_usopen_breakout": COMMON,
    "BOT_C_sp500_london_breakout": COMMON,
    "BOT_E_eurusd_london_breakout": COMMON,
    "BOT_F_nas100_vwap_reversion": [
        Shadow("v2_range_only", "fade only in a POSITIVELY identified range",
               lambda st: None if st.get("d1_regime") in (None, "unknown")
               else st.get("d1_regime") == "range"),
        Shadow("v5_not_extended", "not already 2+ ATR from the D1 mean",
               lambda st: None if st.get("d1_trend_strength_atr") is None
               else abs(st["d1_trend_strength_atr"]) < 2.0),
        Shadow("v3_htf_room", ">=0.5 ATR of room toward the VWAP target", _htf_room),
        Shadow("v4_low_vol", "reversion prefers contracting volatility",
               lambda st: None if st.get("vol_expansion") is None
               else st.get("vol_expansion") <= 1.0),
        Shadow("v6_wide_stop", "stop was at least 0.25 ATR", _wide_stop),
    ],
}


def evaluate(strategy_id: str, state: dict, side: int, sl_dist: float) -> dict:
    """Every variant's verdict at this timestamp. Recorded pre-trade, never revised."""
    st = {**state, "_side": side, "_sl_dist": sl_dist}
    return {s.name: s.evaluate(st) for s in REGISTRY.get(strategy_id, COMMON)}


def log(record: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def scoreboard(closed_trades: list) -> dict:
    """Shadow expectancy = the parent's REAL outcomes, restricted to the trades the variant
    would have taken. Reports skipped/unevaluable counts so a variant cannot look good merely
    by declining to answer."""
    import statistics
    out = {}
    for t in closed_trades:
        sid, R = t.get("strategy_id"), t.get("R")
        sh = t.get("shadows") or {}
        if R is None or not sh:
            continue
        for name, verdict in sh.items():
            k = (sid, name)
            d = out.setdefault(k, {"taken": [], "skipped": [], "unevaluable": 0})
            if verdict is True:
                d["taken"].append(R)
            elif verdict is False:
                d["skipped"].append(R)
            else:
                d["unevaluable"] += 1
    rows = {}
    for (sid, name), d in out.items():
        tk, sk = d["taken"], d["skipped"]
        rows[f"{sid}::{name}"] = {
            "strategy_id": sid, "variant": name,
            "n_taken": len(tk), "n_skipped": len(sk), "n_unevaluable": d["unevaluable"],
            "exp_taken": statistics.fmean(tk) if tk else None,
            "exp_skipped": statistics.fmean(sk) if sk else None,
            "total_R_taken": sum(tk) if tk else 0.0,
            "delta_vs_live": (statistics.fmean(tk) -
                              statistics.fmean(tk + sk)) if (tk and sk) else None,
        }
    return rows
