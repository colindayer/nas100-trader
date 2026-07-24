# VPS_SETUP — correct launch commands and file manifest

**Run everything from ONE directory** (e.g. `C:\Users\Administrator`). The packages must sit beside
each other or `execution_safety` cannot be imported by `market_intel`.

## Full sync (paste as ONE block, then press Enter twice)
```powershell
$B="https://raw.githubusercontent.com/colindayer/nas100-trader/phase404-live-demo"
$V="?v=$(Get-Random)"
mkdir execution_safety,strategy_contracts,market_intel,registry,config -Force | Out-Null
iwr "$B/scripts/portfolio_mt5.py$V"        -OutFile portfolio_mt5.py
iwr "$B/scripts/prop_risk_guardian.py$V"   -OutFile "execution_safety\prop_risk_guardian.py"
"__init__.py","strategy_contract.py","gate.py","execution_guard.py","belief_reader.py",
"guardian_bridge.py","belief_graph_v2.py","operational_belief.py","promotion_pipeline_v2.py",
"demo_evidence.py","position_ledger.py","broker_reconciliation.py","promotion_gate.py",
"prop_objective.py","shadow.py","strategy_registry_shim.py" | % {
    iwr "$B/execution_safety/$_$V" -OutFile "execution_safety\$_" }
"__init__.py","state.py","calendar_feed.py","calendar_provider.py","opportunity.py","engine.py",
"dashboard.py","web.py","telegram_notifier.py","tradingview_bridge.py" | % {
    iwr "$B/market_intel/$_$V" -OutFile "market_intel\$_" }
iwr "$B/strategy_contracts/portfolio_multisleeve.json$V" -OutFile "strategy_contracts\portfolio_multisleeve.json"
iwr "$B/registry/belief_graph.json$V"    -OutFile "registry\belief_graph.json"
iwr "$B/registry/belief_v2.json$V"       -OutFile "registry\belief_v2.json"
iwr "$B/config/guardian.env$V"           -OutFile "config\guardian.env"
```

## Launch commands
| purpose | command |
|--|--|
| shadow book | `py portfolio_mt5.py --config funded` |
| **limited demo execution** | `py portfolio_mt5.py --config funded --demo-limited` |
| **text dashboard** | `py -m market_intel.dashboard --symbols EURUSD,XAUUSD,NAS100` |
| **web dashboard** | `py -m market_intel.web --port 8787` → `http://localhost:8787` |
| symbol discovery | `py portfolio_mt5.py --discover` |
| feed realised results back | `py -c "import sys;sys.path.insert(0,'.');from execution_safety.belief_feedback import run;print(run())"` |

`py -m market_intel.web` requires `market_intel\web.py` to exist — it is **not** in the original
6-file download. Use the full sync above.

## Optional configuration
```powershell
$env:FINNHUB_TOKEN="..."                      # economic calendar (else: no events, by design)
$env:TELEGRAM_TOKEN="..."; $env:TELEGRAM_CHAT_ID="..."
$env:TRADINGVIEW_MCP_URL="http://127.0.0.1:3000"
```

## Expected status lines
- `GUARDIAN BLOCK — GUARDIAN_SNAPSHOT_BAD` → the guardian ran but MT5 gave no usable snapshot
  (terminal closed, or `config/guardian.env` missing). **Fail-closed is correct behaviour.**
- `none loaded` for the calendar → no provider configured. Correct: the system never invents events.
