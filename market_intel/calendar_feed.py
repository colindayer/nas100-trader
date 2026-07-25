"""calendar_feed.py -- PHASE 701 economic calendar. PLUGGABLE by design:
  1. MT5 built-in calendar (if the installed MetaTrader5 build exposes it)
  2. A user-supplied CSV  (market_intel/calendar.csv) -- export from any provider you're licensed for
  3. Empty (engine degrades to technical-only; never fabricates events)
No scraping: sites like Forex Factory publish data but their ToS restricts automated collection, so
the operator supplies the feed. This module NEVER invents an 'actual' value.
"""
from __future__ import annotations
import csv, os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta

CSV_PATH = "market_intel/calendar.csv"
HIGH_IMPACT = {"CPI", "CORE CPI", "PPI", "NFP", "NON-FARM", "FOMC", "ECB", "BOE", "GDP",
               "RETAIL SALES", "ISM", "PMI", "EMPLOYMENT", "INTEREST RATE", "CONSUMER CONFIDENCE",
               "UNEMPLOYMENT", "RATE DECISION"}


@dataclass
class Event:
    event_id: str
    name: str
    currency: str
    scheduled: str                 # ISO UTC
    impact: str                    # high | medium | low
    previous: float | None = None
    forecast: float | None = None
    actual: float | None = None    # None until officially released
    unit: str = ""
    source: str = ""

    # --- surprise maths: only valid once `actual` exists ---
    def released(self) -> bool:
        return self.actual is not None

    def surprise(self):
        if self.actual is None or self.forecast is None:
            return None
        return self.actual - self.forecast

    def surprise_pct(self):
        s = self.surprise()
        if s is None or not self.forecast:
            return None
        return s / abs(self.forecast)

    def to_dict(self): return asdict(self)


def _impact_of(name: str, given: str = "") -> str:
    if given:
        return given.lower()
    up = name.upper()
    return "high" if any(k in up for k in HIGH_IMPACT) else "medium"


def _f(x):
    try:
        return float(str(x).replace("%", "").replace("K", "").replace("M", "").strip())
    except Exception:
        return None


def from_mt5() -> list[Event]:
    """Use MT5's economic calendar if this build exposes it (not all do)."""
    try:
        import MetaTrader5 as mt5
        if not hasattr(mt5, "calendar_value_history"):
            return []
        now = datetime.now(timezone.utc)
        vals = mt5.calendar_value_history(now - timedelta(days=2), now + timedelta(days=7))
        out = []
        for v in vals or []:
            ev = mt5.calendar_event_by_id(v.event_id)
            if ev is None:
                continue
            out.append(Event(event_id=str(v.id), name=ev.name, currency=getattr(ev, "currency", ""),
                             scheduled=str(v.time), impact=_impact_of(ev.name),
                             previous=getattr(v, "prev_value", None),
                             forecast=getattr(v, "forecast_value", None),
                             actual=getattr(v, "actual_value", None), source="mt5"))
        return out
    except Exception:
        return []


def from_csv(path: str = CSV_PATH) -> list[Event]:
    """CSV columns: scheduled,name,currency,impact,previous,forecast,actual,unit"""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            out.append(Event(event_id=f"csv-{i}", name=row.get("name", "?"),
                             currency=row.get("currency", ""), scheduled=row.get("scheduled", ""),
                             impact=_impact_of(row.get("name", ""), row.get("impact", "")),
                             previous=_f(row.get("previous")), forecast=_f(row.get("forecast")),
                             actual=_f(row.get("actual")), unit=row.get("unit", ""), source="csv"))
    return out


def from_api(url: str | None = None, token: str | None = None) -> list[Event]:
    """Auto-fetch from a licensed JSON calendar API. Configure via env:
         CALENDAR_API_URL   e.g. https://finnhub.io/api/v1/calendar/economic
         CALENDAR_API_TOKEN your key
       Understands Finnhub-style {"economicCalendar":[...]} and generic list-of-dicts.
       Returns [] on any failure -- never fabricates."""
    url = url or os.environ.get("CALENDAR_API_URL")
    token = token or os.environ.get("CALENDAR_API_TOKEN", "")
    # convenience: a bare FINNHUB_TOKEN is enough -- build the endpoint for the user
    if not url and os.environ.get("FINNHUB_TOKEN"):
        url = "https://finnhub.io/api/v1/calendar/economic"
        token = os.environ["FINNHUB_TOKEN"]
    if not url:
        return []
    try:
        import urllib.request, json as _json
        full = url + (("&" if "?" in url else "?") + "token=" + token if token else "")
        with urllib.request.urlopen(full, timeout=15) as r:
            data = _json.loads(r.read().decode())
    except Exception:
        return []
    rows = data.get("economicCalendar", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out = []
    for i, d in enumerate(rows):
        name = d.get("event") or d.get("name") or d.get("title") or "?"
        out.append(Event(event_id=str(d.get("id", f"api-{i}")), name=name,
                         currency=d.get("country") or d.get("currency") or "",
                         scheduled=str(d.get("time") or d.get("date") or d.get("scheduled") or ""),
                         impact=_impact_of(name, str(d.get("impact", ""))),
                         previous=_f(d.get("prev") or d.get("previous")),
                         forecast=_f(d.get("estimate") or d.get("forecast")),
                         actual=_f(d.get("actual")), unit=str(d.get("unit", "")), source="api"))
    return out


def from_fred_late() -> list:
    """Late import to avoid a circular import (calendar_provider imports this module).
    Returns EconomicEvent objects -- same duck-typed interface as Event."""
    try:
        from .fred_provider import load as _fred
        return _fred()
    except Exception:
        return []


def load() -> list:
    """API (auto) -> MT5 built-in -> FRED (free/official) -> operator CSV -> empty.
    Never fabricates an actual."""
    return from_api() or from_mt5() or from_fred_late() or from_csv()


def upcoming(events: list[Event], now: datetime | None = None, hours=24) -> list[Event]:
    now = now or datetime.now(timezone.utc)
    out = []
    for e in events:
        try:
            t = datetime.fromisoformat(e.scheduled.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if now <= t <= now + timedelta(hours=hours):
            out.append(e)
    return sorted(out, key=lambda x: x.scheduled)


def just_released(events: list[Event]) -> list[Event]:
    """Events whose official Actual now exists -> the ONLY ones allowed to create opportunities."""
    return [e for e in events if e.released()]
