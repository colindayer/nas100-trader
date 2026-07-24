# TRADINGVIEW_MCP

Optional. TradingView has no public market-data API; community MCP servers drive **TradingView
Desktop** over the Chrome DevTools Protocol.

## Known servers
- [tradesdontlie/tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp) — original
- [LewisWJackson/tradingview-mcp-jackson](https://github.com/LewisWJackson/tradingview-mcp-jackson) — adds morning brief; fixes Desktop v2.14+ launch
- [atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp) — data, screeners, backtesting
- [bidouilles/mcp-tradingview-server](https://github.com/bidouilles/mcp-tradingview-server) — FastMCP indicators + OHLCV

## Wiring
```
TRADINGVIEW_MCP_URL=http://127.0.0.1:3000
```
`tradingview_bridge.available()` health-checks it; on any failure `chart_context()` returns
`{"source": "mt5_fallback"}`. Proven by `test_tradingview_falls_back_without_mcp`.

## Authority rule
**MT5 is authoritative for every trading decision.** TradingView context is advisory only —
`enrich()` returns `"authority": "mt5"`. Rationale: MT5 prices are the prices you actually fill at.
