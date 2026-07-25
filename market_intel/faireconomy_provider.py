"""faireconomy_provider.py -- FREE calendar WITH consensus forecasts, no scraping, no key.

ForexFactory publishes its calendar as a JSON feed via FairEconomy:
    https://nfs.faireconomy.media/ff_calendar_thisweek.json
This is a PUBLISHED endpoint intended for consumption (widely used by EAs) -- not HTML scraping,
so it does not have the ToS problem the scraper repos do. It provides title/country/date/impact/
forecast/previous, and `actual` once released.
"""
from __future__ import annotations
import json, os, re, ssl, urllib.request
from datetime import datetime, timezone
from .calendar_provider import EconomicEvent

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",   # 404s at times; tolerated
]
TIMEOUT = 15
CACHE = "registry/faireconomy_cache.json"


def _ssl_ctx():
    """Windows Python does not use the OS certificate store, so some chains fail to verify.
    Prefer `truststore` (real Windows store), then `certifi`, then the default context.
      py -m pip install truststore     # best on Windows
      py -m pip install --upgrade certifi
    Verification is NEVER disabled here."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
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
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx()) as r:
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


def diagnose():
    """Print the RAW result of each feed fetch. Run: py -m market_intel.faireconomy_provider"""
    import urllib.error, ssl, time
    ctx = _ssl_ctx()
    impl = type(ctx).__module__
    print(f"TLS context: {impl} ({'truststore/Windows store' if 'truststore' in impl else 'certifi/default bundle'})")
    try:
        import certifi; print(f"certifi: {certifi.__version__} @ {certifi.where()}")
    except Exception: print("certifi: NOT INSTALLED  ->  py -m pip install --upgrade certifi")
    try:
        import truststore; print("truststore: installed (uses the Windows cert store)")
    except Exception: print("truststore: not installed  ->  py -m pip install truststore  (recommended on Windows)")
    print(f"cache: {CACHE} exists={os.path.exists(CACHE)}")
    rows, age = _cache_read()
    print(f"cache rows={len(rows) if rows else 0} age={None if age is None else round(age)}s ttl={CACHE_TTL}s")
    for url in FEEDS:
        print(f"\n--- {url}")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) calendar-client",
                "Accept": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx()) as r:
                body = r.read().decode()
            print(f"HTTP {r.status}  {len(body)} bytes  {(time.time()-t0)*1000:.0f}ms")
            try:
                d = json.loads(body)
                print(f"parsed {len(d)} rows; first: {json.dumps(d[0])[:160] if d else '(none)'}")
            except Exception as e:
                print(f"JSON parse failed: {e}\nbody[:200]: {body[:200]}")
        except urllib.error.HTTPError as e:
            print(f"HTTPError {e.code} {e.reason}")
            try: print("body:", e.read().decode()[:200])
            except Exception: pass
        except urllib.error.URLError as e:
            print(f"URLError: {e.reason}  <- network/DNS/TLS blocked?")
        except ssl.SSLError as e:
            print(f"SSLError: {e}")
        except Exception as e:
            print(f"{type(e).__name__}: {e}")


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


if __name__ == "__main__":
    diagnose()
    print("\n--- load() ---")
    ev = load()
    print(f"{len(ev)} events; with forecast: {sum(1 for e in ev if e.forecast is not None)}")
