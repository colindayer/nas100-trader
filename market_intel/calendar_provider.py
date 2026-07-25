"""calendar_provider.py -- PHASE 701. Pluggable economic calendar with an explicit priority chain:
    MT5 Economic Calendar -> Finnhub -> Trading Economics -> FXStreet -> CSV
plus an OPTIONAL Forex Factory adapter that is DISABLED by default (their ToS restricts automated
collection; enable only if you have permission: set FOREXFACTORY_ENABLED=1 and FOREXFACTORY_URL).

Normalises everything into EconomicEvent. Never fabricates an `actual`.
"""
from __future__ import annotations
import json, os, urllib.parse, urllib.request
from dataclasses import dataclass, asdict, field
from .calendar_feed import Event, _impact_of, _f, from_mt5, from_csv

TIMEOUT = 15
HIST = "registry/calendar_history.json"


@dataclass
class EconomicEvent:
    event_id: str
    name: str
    country: str
    currency: str
    scheduled: str
    impact: str
    previous: float | None = None
    forecast: float | None = None
    actual: float | None = None
    unit: str = ""
    provider: str = ""
    historical_reaction: dict = field(default_factory=dict)

    def released(self): return self.actual is not None
    def surprise(self):
        return None if (self.actual is None or self.forecast is None) else self.actual - self.forecast
    def surprise_pct(self):
        s = self.surprise()
        return None if (s is None or not self.forecast) else s / abs(self.forecast)
    def to_dict(self): return asdict(self)


def _norm(d, provider, idx) -> EconomicEvent:
    name = d.get("event") or d.get("name") or d.get("title") or d.get("Category") or "?"
    return EconomicEvent(
        event_id=str(d.get("id") or d.get("CalendarId") or f"{provider}-{idx}"), name=name,
        country=str(d.get("country") or d.get("Country") or ""),
        currency=str(d.get("currency") or d.get("Currency") or d.get("country") or ""),
        scheduled=str(d.get("time") or d.get("date") or d.get("Date") or d.get("dateUtc") or ""),
        impact=_impact_of(name, str(d.get("impact") or d.get("Importance") or "")),
        previous=_f(d.get("prev") or d.get("previous") or d.get("Previous")),
        forecast=_f(d.get("estimate") or d.get("forecast") or d.get("Forecast") or d.get("consensus")),
        actual=_f(d.get("actual") or d.get("Actual")),
        unit=str(d.get("unit") or ""), provider=provider)


def _http_json(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def from_finnhub() -> list[EconomicEvent]:
    tok = os.environ.get("FINNHUB_TOKEN")
    if not tok: return []
    d = _http_json(f"https://finnhub.io/api/v1/calendar/economic?token={tok}")
    rows = (d or {}).get("economicCalendar", []) if isinstance(d, dict) else []
    return [_norm(x, "finnhub", i) for i, x in enumerate(rows)]


def from_trading_economics() -> list[EconomicEvent]:
    key = os.environ.get("TRADINGECONOMICS_KEY")
    if not key: return []
    d = _http_json(f"https://api.tradingeconomics.com/calendar?c={key}&f=json")
    return [_norm(x, "tradingeconomics", i) for i, x in enumerate(d or [])] if isinstance(d, list) else []


def from_fxstreet() -> list[EconomicEvent]:
    url = os.environ.get("FXSTREET_URL")
    if not url: return []
    d = _http_json(url)
    rows = d if isinstance(d, list) else (d or {}).get("events", [])
    return [_norm(x, "fxstreet", i) for i, x in enumerate(rows)]


def from_forexfactory() -> list[EconomicEvent]:
    """DISABLED unless explicitly permitted. Forex Factory's ToS restricts automated collection."""
    if os.environ.get("FOREXFACTORY_ENABLED") != "1":
        return []
    url = os.environ.get("FOREXFACTORY_URL")
    if not url: return []
    d = _http_json(url)
    rows = d if isinstance(d, list) else (d or {}).get("events", [])
    return [_norm(x, "forexfactory", i) for i, x in enumerate(rows)]


def _from_legacy(fn, provider) -> list[EconomicEvent]:
    out = []
    for e in fn():
        out.append(EconomicEvent(event_id=e.event_id, name=e.name, country=e.currency,
                                 currency=e.currency, scheduled=e.scheduled, impact=e.impact,
                                 previous=e.previous, forecast=e.forecast, actual=e.actual,
                                 unit=e.unit, provider=provider))
    return out


def from_faireconomy():
    from .faireconomy_provider import load as _ff
    return _ff()


def from_fred():
    from .fred_provider import load as _fred
    return _fred()


PROVIDERS = [("faireconomy", from_faireconomy),
             ("mt5", lambda: _from_legacy(from_mt5, "mt5")), ("finnhub", from_finnhub),
             ("fred", from_fred),
             ("tradingeconomics", from_trading_economics), ("fxstreet", from_fxstreet),
             ("forexfactory", from_forexfactory), ("csv", lambda: _from_legacy(from_csv, "csv"))]


def load() -> tuple[list[EconomicEvent], str]:
    """Returns (events, provider_used). First provider that yields data wins."""
    for name, fn in PROVIDERS:
        try:
            ev = fn()
        except Exception:
            ev = []
        if ev:
            return attach_history(ev), name
    return [], "none"


def attach_history(events: list[EconomicEvent]) -> list[EconomicEvent]:
    """Attach historical reaction stats if we have recorded any (never invented)."""
    if not os.path.exists(HIST):
        return events
    try:
        hist = json.load(open(HIST))
    except Exception:
        return events
    for e in events:
        h = hist.get(e.name)
        if h:
            e.historical_reaction = h
    return events


def record_reaction(event: EconomicEvent, symbol: str, move_pct: float, path=HIST):
    """Record what a market actually did after a release, to build real historical context."""
    hist = json.load(open(path)) if os.path.exists(path) else {}
    h = hist.setdefault(event.name, {"observations": []})
    h["observations"].append({"symbol": symbol, "surprise": event.surprise(),
                              "move_pct": move_pct, "scheduled": event.scheduled})
    obs = [o["move_pct"] for o in h["observations"]]
    h["n"] = len(obs); h["mean_move_pct"] = sum(obs) / len(obs)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(hist, open(path, "w"), indent=1)
    return h
