"""fred_provider.py -- FREE, OFFICIAL, no-ToS-problem economic data.

FRED (Federal Reserve Bank of St. Louis) publishes US macro series and their RELEASE DATES.
Free API key, no rate-limit games, no scraping: https://fredaccount.stlouisfed.org/apikeys

HONEST LIMITATION: FRED publishes `previous` and `actual`. It does NOT publish consensus
`forecast` -- consensus is a commercial product everywhere. So surprise-vs-forecast is unavailable
from this source; what you get instead is actual-vs-previous (a weaker but real signal).
The engine already refuses to compute a surprise when forecast is None, so nothing is faked.

Env: FRED_API_KEY
"""
from __future__ import annotations
import json, os, urllib.request
from datetime import datetime, timedelta, timezone
from .calendar_provider import EconomicEvent

BASE = "https://api.stlouisfed.org/fred"
TIMEOUT = 15

# series_id -> (display name, currency, impact)
SERIES = {
    "CPIAUCSL": ("US CPI (all items)", "USD", "high"),
    "CPILFESL": ("US Core CPI", "USD", "high"),
    "PAYEMS":   ("US Nonfarm Payrolls", "USD", "high"),
    "UNRATE":   ("US Unemployment Rate", "USD", "high"),
    "PPIACO":   ("US PPI (all commodities)", "USD", "high"),
    "GDPC1":    ("US Real GDP", "USD", "high"),
    "RSAFS":    ("US Retail Sales", "USD", "high"),
    "FEDFUNDS": ("US Fed Funds Rate", "USD", "high"),
    "INDPRO":   ("US Industrial Production", "USD", "medium"),
    "UMCSENT":  ("US Consumer Sentiment", "USD", "medium"),
}


def _get(path, **params):
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return None
    params.update(api_key=key, file_type="json")
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        with urllib.request.urlopen(f"{BASE}/{path}?{q}", timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


import urllib.parse  # noqa: E402


def latest(series_id: str) -> tuple[float | None, float | None, str]:
    """(previous, actual, date) from the two most recent observations."""
    d = _get("series/observations", series_id=series_id, sort_order="desc", limit=2)
    obs = (d or {}).get("observations", [])
    def f(x):
        try: return float(x)
        except Exception: return None
    if len(obs) >= 2:
        return f(obs[1]["value"]), f(obs[0]["value"]), obs[0]["date"]
    if obs:
        return None, f(obs[0]["value"]), obs[0]["date"]
    return None, None, ""


def upcoming_releases(days=30) -> dict:
    """release_id -> next release date, from FRED's official release calendar."""
    today = datetime.now(timezone.utc).date()
    d = _get("releases/dates", realtime_start=str(today),
             realtime_end=str(today + timedelta(days=days)), include_release_dates_with_no_data="true",
             sort_order="asc", limit=1000)
    out = {}
    for r in (d or {}).get("release_dates", []):
        out.setdefault(r["release_id"], r["date"])
    return out


def load() -> list[EconomicEvent]:
    """Build EconomicEvents from FRED. forecast is None BY DESIGN (FRED has no consensus)."""
    if not os.environ.get("FRED_API_KEY"):
        return []
    out = []
    for sid, (name, ccy, impact) in SERIES.items():
        prev, act, date = latest(sid)
        if act is None:
            continue
        out.append(EconomicEvent(
            event_id=f"fred-{sid}", name=name, country="US", currency=ccy,
            scheduled=f"{date}T13:30:00+00:00" if date else "",
            impact=impact, previous=prev, forecast=None, actual=act,
            unit="index/level", provider="fred",
            historical_reaction={"note": "FRED provides actual+previous; consensus forecast "
                                         "is not available from any free official source"}))
    return out
