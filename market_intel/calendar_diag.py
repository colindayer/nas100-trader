"""calendar_diag.py -- diagnose why a calendar provider returns nothing. Prints the RAW response.
Run: py -m market_intel.calendar_diag
"""
import json, os, urllib.request, urllib.error

def probe(name, url):
    print(f"\n--- {name} ---\n{url.split('token=')[0]}token=***")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            body = r.read().decode()[:600]
            print(f"HTTP {r.status}")
            print(body if body.strip() else "(empty body)")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.reason}")
        try: print(e.read().decode()[:400])
        except Exception: pass
    except Exception as e:
        print(f"ERROR {type(e).__name__}: {e}")

if __name__ == "__main__":
    fh = os.environ.get("FINNHUB_TOKEN")
    print("FINNHUB_TOKEN set:", bool(fh))
    if fh:
        probe("finnhub economic calendar",
              f"https://finnhub.io/api/v1/calendar/economic?token={fh}")
        probe("finnhub quote (free-tier sanity check)",
              f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={fh}")
    te = os.environ.get("TRADINGECONOMICS_KEY")
    print("\nTRADINGECONOMICS_KEY set:", bool(te))
    if te:
        probe("trading economics calendar",
              f"https://api.tradingeconomics.com/calendar?c={te}&f=json")
    print("\nguest key available for Trading Economics: c=guest:guest")
    probe("trading economics GUEST", "https://api.tradingeconomics.com/calendar?c=guest:guest&f=json")
