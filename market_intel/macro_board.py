"""macro_board.py -- Macro Board. Read-only regime evidence for the dashboard.

DISCIPLINE (from QUANT_OS_ARCHITECTURE):
  * every claim carries its evidence, its sources and its as-of time
  * contradictions are DISPLAYED, never resolved
  * unknowns are enumerated -- a missing source is a first-class output
  * emits NO direction, NO signal, NO score that could be read as edge probability

It reads what already exists (MT5 prices + calendar_feed) and classifies. No new provider.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# cross-asset proxies -> macro dimension. Broker names resolved at call time.
PROXIES = {
    "dollar":      ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"],
    "commodities": ["XAUUSD", "XAGUSD", "WTOIL-PERP", "Copper"],
    "equities":    ["NAS100", "US500", "US30"],
    "crypto":      ["BTCUSD", "ETHUSD"],
}
HIGH_IMPACT_TAGS = ("CPI", "NFP", "NON-FARM", "FOMC", "ECB", "BOE", "GDP", "RATE", "PMI", "ISM",
                    "UNEMPLOYMENT", "RETAIL")


@dataclass
class Claim:
    dimension: str
    statement: str
    evidence: list = field(default_factory=list)      # [(what, value, source)]
    contradictions: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    confidence: float = 0.0                           # evidence coverage ONLY, not edge probability
    as_of: str = ""

    def to_dict(self): return asdict(self)


def _pct(series_now, series_then):
    try:
        return (series_now / series_then - 1.0)
    except Exception:
        return None


def _mt5_change(sym, bars=21):
    """(last, pct_change_over_bars, source) from daily bars. None if unavailable."""
    try:
        import MetaTrader5 as mt5
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, bars + 1)
        if r is None or len(r) < bars:
            return None, None, None
        last = float(r[-1]["close"]); prev = float(r[0]["close"])
        return last, _pct(last, prev), f"MT5:{sym}:D1"
    except Exception:
        return None, None, None


def _resolve(names):
    """Return the first broker symbol that exists, else None."""
    try:
        import MetaTrader5 as mt5
        for n in names:
            if mt5.symbol_info(n) is not None:
                return n
    except Exception:
        pass
    return None


def _dimension(dim: str, syms: list, now_iso: str) -> Claim:
    ev, unknown, moves = [], [], []
    for want in syms:
        s = _resolve([want])
        if s is None:
            unknown.append(f"{want} not in Market Watch")
            continue
        last, chg, src = _mt5_change(s)
        if chg is None:
            unknown.append(f"{s} no daily history")
            continue
        ev.append((s, f"{chg:+.2%} (21d)", src))
        moves.append(chg)
    if not moves:
        return Claim(dim, "UNKNOWN — no usable data", [], [], unknown, 0.0, now_iso)
    mean = sum(moves) / len(moves)
    up = sum(1 for m in moves if m > 0)
    # contradiction = constituents disagree in direction
    contra = []
    if 0 < up < len(moves):
        contra.append(f"constituents disagree: {up}/{len(moves)} up")
    label = "rising" if mean > 0.005 else "falling" if mean < -0.005 else "flat"
    conf = round(len(moves) / max(len(syms), 1) * (1.0 if not contra else 0.6), 2)
    return Claim(dim, f"{dim} {label} ({mean:+.2%} 21d avg)", ev, contra, unknown, conf, now_iso)


def _volatility_claim(now_iso: str) -> Claim:
    """Vol proxy from index true range percentile — we have no VIX feed, and say so."""
    s = _resolve(PROXIES["equities"])
    if s is None:
        return Claim("volatility", "UNKNOWN", [], [], ["no equity index available"], 0.0, now_iso)
    try:
        import MetaTrader5 as mt5, statistics as st
        r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 260)
        if r is None or len(r) < 60:
            return Claim("volatility", "UNKNOWN", [], [], ["insufficient history"], 0.0, now_iso)
        rng = [float(x["high"] - x["low"]) / float(x["close"]) for x in r]
        recent = st.mean(rng[-20:])
        pct = sum(1 for v in rng if v < recent) / len(rng)
        lab = "elevated" if pct > 0.7 else "subdued" if pct < 0.3 else "normal"
        return Claim("volatility", f"volatility {lab} ({pct:.0%} percentile, 1y)",
                     [(s, f"20d mean range {recent:.2%}", f"MT5:{s}:D1")], [],
                     ["no VIX feed wired — index range is a proxy, not the VIX"], 0.75, now_iso)
    except Exception as e:
        return Claim("volatility", "UNKNOWN", [], [], [f"error: {type(e).__name__}"], 0.0, now_iso)


def _risk_claim(claims: dict, now_iso: str) -> Claim:
    """Risk-on/off SYNTHESISED from the other claims. Never a standalone assertion."""
    ev, contra = [], []
    eq = claims.get("equities"); vol = claims.get("volatility"); gold = claims.get("commodities")
    score = 0
    if eq and "rising" in eq.statement: score += 1; ev.append(("equities", "rising", "derived"))
    if eq and "falling" in eq.statement: score -= 1; ev.append(("equities", "falling", "derived"))
    if vol and "elevated" in vol.statement: score -= 1; ev.append(("volatility", "elevated", "derived"))
    if vol and "subdued" in vol.statement: score += 1; ev.append(("volatility", "subdued", "derived"))
    if not ev:
        return Claim("risk", "UNKNOWN", [], [], ["no constituent claims available"], 0.0, now_iso)
    label = "risk-on" if score > 0 else "risk-off" if score < 0 else "mixed"
    if score == 0:
        contra.append("constituents net to zero — do not read a regime from this")
    return Claim("risk", f"regime {label}", ev, contra,
                 ["no positioning data (COT unwired)", "no credit spreads"],
                 round(min(1.0, abs(score) / 2), 2), now_iso)


def upcoming_high_impact(hours=48):
    """From the working calendar. Returns [] honestly if no provider is available."""
    try:
        from . import calendar_feed as cal
        evs = cal.load()
        now = datetime.now(timezone.utc)
        out = []
        for e in evs:
            nm = (e.name or "").upper()
            if not any(t in nm for t in HIGH_IMPACT_TAGS):
                continue
            try:
                t = datetime.fromisoformat(str(e.scheduled).replace("Z", "+00:00"))
                if t.tzinfo is None: t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            mins = (t - now).total_seconds() / 60
            if 0 <= mins <= hours * 60:
                out.append({"name": e.name, "currency": e.currency, "in_minutes": int(mins),
                            "previous": e.previous, "forecast": e.forecast, "actual": e.actual,
                            "provider": getattr(e, "provider", "?")})
        return sorted(out, key=lambda x: x["in_minutes"])
    except Exception:
        return []


def latest_releases(limit=6):
    """Released events WITH a surprise. Never fabricates one."""
    try:
        from . import calendar_feed as cal
        out = []
        for e in cal.load():
            if e.actual is None or e.forecast is None:
                continue
            s = e.surprise()
            if s is None:
                continue
            out.append({"name": e.name, "currency": e.currency, "actual": e.actual,
                        "forecast": e.forecast, "surprise": s,
                        "surprise_pct": e.surprise_pct(), "scheduled": e.scheduled,
                        "provider": getattr(e, "provider", "?")})
        return out[-limit:][::-1]
    except Exception:
        return []


def board() -> dict:
    """Full Macro Board. Every claim carries evidence, contradictions and unknowns."""
    now_iso = datetime.now(timezone.utc).isoformat()
    claims = {}
    for dim, syms in PROXIES.items():
        claims[dim] = _dimension(dim, syms, now_iso)
    claims["volatility"] = _volatility_claim(now_iso)
    claims["risk"] = _risk_claim(claims, now_iso)
    return {"as_of": now_iso,
            "claims": {k: v.to_dict() for k, v in claims.items()},
            "upcoming_high_impact": upcoming_high_impact(),
            "latest_releases": latest_releases(),
            "note": "Evidence only. No direction, no signal, no edge probability. "
                    "'confidence' is evidence COVERAGE, not probability of profit."}
