"""tradingview_bridge.py -- PHASE 701. Optional TradingView MCP integration with an MT5 fallback.

If a TradingView MCP server is reachable (e.g. tradesdontlie/tradingview-mcp, which drives
TradingView Desktop over Chrome DevTools Protocol), chart context can be read through it.
Otherwise this transparently falls back to MT5-derived analysis, which is what we already trust.

READ-ONLY. No order functions. Never fabricates chart data: if a source is unavailable it says so.
"""
from __future__ import annotations
import json, os, urllib.request

MCP_URL = os.environ.get("TRADINGVIEW_MCP_URL")        # e.g. http://127.0.0.1:3000
TIMEOUT = 8


def available() -> tuple[bool, str]:
    if not MCP_URL:
        return False, "TRADINGVIEW_MCP_URL not set — using MT5 fallback"
    try:
        with urllib.request.urlopen(f"{MCP_URL}/health", timeout=TIMEOUT) as r:
            return (r.status == 200), f"MCP {r.status}"
    except Exception as e:
        return False, f"MCP unreachable ({str(e)[:60]}) — using MT5 fallback"


def chart_context(symbol: str, timeframe: str = "15") -> dict:
    """Chart context from TradingView MCP if available, else {'source':'mt5_fallback'}."""
    ok, why = available()
    if not ok:
        return {"source": "mt5_fallback", "reason": why, "symbol": symbol}
    try:
        q = urllib.parse.urlencode({"symbol": symbol, "timeframe": timeframe})
        with urllib.request.urlopen(f"{MCP_URL}/chart?{q}", timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        return {"source": "tradingview_mcp", "symbol": symbol, "timeframe": timeframe, **data}
    except Exception as e:
        return {"source": "mt5_fallback", "reason": f"MCP error {str(e)[:60]}", "symbol": symbol}


def enrich(state) -> dict:
    """Merge MT5-derived MarketState with TradingView context when present. MT5 remains the
    authority for anything used in a trading decision."""
    ctx = chart_context(state.symbol)
    return {"market_state": state.to_dict(), "tradingview": ctx,
            "authority": "mt5",   # MT5 prices are what we actually trade on
            "note": "TradingView context is advisory only; MT5 is authoritative for decisions."}
