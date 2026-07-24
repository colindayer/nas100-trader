# CALENDAR_PROVIDER

Pluggable economic calendar. **Never fabricates an `actual`.**

## Priority chain
`MT5 Economic Calendar → Finnhub → Trading Economics → FXStreet → CSV`
First provider returning data wins; the provider used is recorded on every event.

**Forex Factory** — adapter exists but is **disabled by default**. Their ToS restricts automated
collection. Enable only with permission: `FOREXFACTORY_ENABLED=1` + `FOREXFACTORY_URL`.

## Configuration
```
FINNHUB_TOKEN=...             # https://finnhub.io/docs/api/economic-calendar
TRADINGECONOMICS_KEY=...      # https://tradingeconomics.com/api/calendar.aspx
FXSTREET_URL=...              # https://docs.fxstreet.com/api/calendar/
```
Or drop `market_intel/calendar.csv`: `scheduled,name,currency,impact,previous,forecast,actual,unit`.

## EconomicEvent
`event_id · name · country · currency · scheduled · impact · previous · forecast · actual · unit ·
provider · historical_reaction`

`surprise = actual − forecast` and `surprise_pct` return **None** until `actual` exists — enforced by
`test_economic_event_no_surprise_before_actual`.

## Historical reaction
`record_reaction(event, symbol, move_pct)` appends a real observed post-release move and maintains
`n` / `mean_move_pct` in `registry/calendar_history.json`. Only measured moves — nothing modelled.
