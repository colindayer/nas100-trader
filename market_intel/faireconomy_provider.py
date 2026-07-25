"""faireconomy_provider.py -- FREE calendar WITH consensus forecasts, no scraping, no key.

ForexFactory publishes its calendar as a JSON feed via FairEconomy:
    https://nfs.faireconomy.media/ff_calendar_thisweek.json
This is a PUBLISHED endpoint intended for consumption (widely used by EAs) -- not HTML scraping,
so it does not have the ToS problem the scraper repos do. It provides title/country/date/impact/
forecast/previous, and `actual` once released.
"""
from __future__ import annotations
import json, os, re, urllib.request
from datetime import datetime, timezone
from .calendar_provider import EconomicEvent

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",   # 404s at times; tolerated
]
TIMEOUT = 15
CACHE = "registry/faireconomy_cache.json"
CACHE_TTL = 900          # 15 min: the feed rate-limits (HTTP 429); be a good citizen
_IMPACT = {"high": "high", "medium": "medium", "low": "low", "holiday": "low"}


def _num(x):
    """'250M' -> 250e6 ; '3.00%' -> 3.0 ; '-0.6%' -> -0.6 ; '' -> None"""
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    m = re.match(r"^(-?\d*\.?\d+)\s*([KMBT])?$", s, re.I)
    if not m:
        try: return float(s)
        except Exception: return None
    v = float(m.group(1))
    return v * {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}.get((m.group(2) or "").lower(), 1)


def _cache_read():
    """Return (rows, age_seconds) from the on-disk cache, or (None, None)."""
    if not os.path.exists(CACHE):
        return None, None
    try:
        import time
        age = time.time() - os.path.getmtime(CACHE)
        return json.load(open(CACHE)), age
    except Exception:
        return None, None


def _cache_write(rows):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(rows, open(CACHE, "w"))
    except Exception:
        pass


def _fetch(url):
    """Fetch one feed. Callers must go through _fetch_all() so the cache is respected."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) calendar-client",
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []


def _fetch_all():
    """Cached fetch. Serves cache while fresh; on 429/failure serves STALE cache rather than
    pretending there are no events."""
    rows, age = _cache_read()
    if rows is not None and age is not None and age < CACHE_TTL:
        return rows
    fresh = []
    for url in FEEDS:
        fresh.extend(_fetch(url) or [])
    if fresh:
        _cache_write(fresh)
        return fresh
    return rows or []          # rate-limited/offline -> last known good, never fabricated


def load() -> list[EconomicEvent]:
    if os.environ.get("FAIRECONOMY_DISABLED") == "1":
        return []
    out, seen = [], set()
    if True:
        for i, d in enumerate(_fetch_all()):
            title = d.get("title") or "?"
            when = str(d.get("date") or "")
            key = (title, when, d.get("country"))
            if key in seen:
                continue
            seen.add(key)
            try:                                    # normalise to UTC ISO
                when_iso = datetime.fromisoformat(when).astimezone(timezone.utc).isoformat()
            except Exception:
                when_iso = when
            out.append(EconomicEvent(
                event_id=f"ff-{abs(hash(key)) % 10**10}", name=title,
                country=str(d.get("country") or ""), currency=str(d.get("country") or ""),
                scheduled=when_iso,
                impact=_IMPACT.get(str(d.get("impact", "")).lower(), "medium"),
                previous=_num(d.get("previous")), forecast=_num(d.get("forecast")),
                actual=_num(d.get("actual")), unit="", provider="faireconomy"))
    return out
