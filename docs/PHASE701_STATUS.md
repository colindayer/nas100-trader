# PHASE701_STATUS

## Built and tested
| module | status | notes |
|--|--|--|
| `calendar_provider.py` | ✅ | priority chain MT5 → Finnhub → TradingEconomics → FXStreet → CSV; Forex Factory adapter present but **disabled by default** (ToS); `EconomicEvent` with previous/forecast/actual/surprise/impact/country/currency/historical_reaction; `record_reaction()` builds real history |
| `tradingview_bridge.py` | ✅ | optional MCP integration (`TRADINGVIEW_MCP_URL`), transparent MT5 fallback; **MT5 stays authoritative** for any decision |
| `telegram_notifier.py` | ✅ | 9 alert classes, confidence filter, append-only alert log, fails gracefully unconfigured |
| `market_classifier.py` | ↔ `state.py` | existing module already classifies trend/vol/session/kill-zones/sweeps/FVG/OB/structure/VWAP/ATR |
| `opportunity_registry.py` | ↔ `opportunity.py` | existing Opportunity + append-only registry with all required fields |
| `market_engine.py` | ↔ `engine.py` | existing orchestrator: pre-event reports, post-Actual opportunities, routes through the gate, fails closed |
| `web.py` | ✅ (partial) | live dashboard; **does not yet render the two beliefs separately or Telegram status** |

Tests: **9/9** new-module guarantees (`test_phase701b.py`) + **6/6** engine guarantees (`test_intel.py`),
including structural proof that no market-intelligence module references an order call.

## Governance
Unchanged and unbypassed. Opportunities flow Market Intelligence → Opportunity Registry → Belief
Graph → Guardian → Promotion Pipeline → Shadow → Limited Demo → Full Demo → Live. No module in this
phase can place a trade; `test_telegram_never_places_orders` and `test_package_cannot_place_orders`
enforce it structurally.

## NOT yet built (honest)
1. **Challenge Mode** (conviction scaling / optional pyramiding gated by contract + Guardian + prop
   rules, with logged evidence and exposure). **Not started.**
2. **Dashboard v2** — separate Research/Operational belief panes, liquidity map, FVG/OB overlays,
   opportunity queue, Telegram status, system health.
3. **Full audit records** for every `GuardianDecision` / `BeliefUpdate` / `PromotionDecision` /
   `TelegramAlert` / `ShadowTrade` — currently partial (intel log, telegram log, demo evidence ledger,
   position ledger exist; a unified audit index does not).
4. Docs still to write: `MARKET_INTELLIGENCE.md`, `CALENDAR_PROVIDER.md`, `TRADINGVIEW_MCP.md`,
   `TELEGRAM.md`, `OPPORTUNITY_REGISTRY.md`.
5. Historical-reaction percentiles are recorded but not yet used to score opportunity confidence.

## Configuration
```
FINNHUB_TOKEN=...            # or TRADINGECONOMICS_KEY / FXSTREET_URL
TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...  TELEGRAM_MIN_CONFIDENCE=0.5
TRADINGVIEW_MCP_URL=http://127.0.0.1:3000   # optional; MT5 fallback otherwise
```

## Risks
- Telegram alerts are advisory; they must never be read as instructions to trade manually.
- TradingView MCP is third-party and drives a desktop app; treat its output as advisory context only.
- Calendar providers disagree on timestamps/units; the provider used is recorded per event.
