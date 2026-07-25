# DEPLOYMENT_PACKAGE

**Blocking finding:** `MANIFEST.json` is at commit `c9600ae` while HEAD is `988f366`, and it does
**not** list `execution_safety/safety_state.py` or `execution_safety/startup_reconciler.py` — the two
modules that close V-01/02/04/12. **Regenerate the manifest before deploying**, or the VPS will pass
`--verify` while missing the critical fixes.

```
py deploy.py --manifest        # on the source machine, FIRST
py deploy.py --sync-script     # emits the SHA-pinned PowerShell
```

## 1. File list (36 after regeneration)
| dir | files |
|--|--|
| `./` | `VERSION.json`, `deploy.py`, `healthcheck.py`, `startup.py` |
| `execution_safety/` | `__init__`, `gate`, `strategy_contract`, `execution_guard`, `belief_graph_v2`, `promotion_pipeline_v2`, `operational_belief`, `demo_evidence`, `position_ledger`, `broker_reconciliation`, `guardian_bridge`, `belief_reader`, `shadow`, `promotion_gate`, **`safety_state`**, **`startup_reconciler`** |
| `market_intel/` | `__init__`, `state`, `calendar_feed`, `calendar_provider`, `faireconomy_provider`, `fred_provider`, `opportunity`, `engine`, `dashboard`, `web`, `telegram_notifier`, `tradingview_bridge`, `reaction_recorder` |
| `scripts/` | `portfolio_mt5.py`, `prop_risk_guardian.py` |
| `strategy_contracts/` | `portfolio_multisleeve.json` |
| `config/` | `guardian.env` |
| `registry/` | created empty; state bootstraps on first run |

**Explicitly NOT deployed:** `live_trader.py`, `mt5_broker.py` (BANNED_EXECUTORS — caused the incident).

## 2. Deployment order
1. `py deploy.py --manifest` (source machine) → regenerates with current SHA
2. `py deploy.py --sync-script` → copy output
3. On VPS: stop everything — MT5 AutoTrading OFF; disable all scheduled tasks
4. **Export MT5 history for 61552095** (Journal, Experts, Reports) — irreplaceable evidence
5. Paste the sync block
6. `py deploy.py --verify` → must read **COMPLETE**
7. `py deploy.py --scan-executors` → must read **CLEAN**
8. `py healthcheck.py` → **0 critical failures**
9. `py startup.py` → confirm version, DEMO account, promotion state, guardian

## 3. Verification order (never reorder — each gates the next)
`--verify` → `--scan-executors` → `healthcheck` → `startup` → shadow run → *stop*.
Demo execution requires separate approval.

## 4. Rollback
```powershell
py deploy.py --sync-script   # regenerate from a KNOWN-GOOD commit SHA instead of HEAD
```
Every deployment is a SHA-pinned file set, so rollback = re-sync from the previous SHA.
**`registry/` is never rolled back** — safety state and ledgers are append-only history.
If a rollback crosses a `SCHEMA_VERSION` change, `safety_state.load()` fails closed (halted) by
design; clear only via `clear_halt('human:<name>')` after confirming the state is sane.

## 5. Dependency checks
```powershell
py -c "import MetaTrader5, pandas, numpy, truststore, certifi; print('deps ok')"
```
`truststore` is required — Windows Python does not use the OS certificate store and the calendar
feed will fail TLS verification without it.

## 6. Environment variables
| var | required | purpose |
|--|--|--|
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | optional | alerts (**no runner emits them yet**) |
| `FRED_API_KEY` | optional | fallback calendar (no forecasts) |
| `GUARDIAN_CONFIG` | optional | defaults to `config/guardian.env` |
| `TRADINGVIEW_MCP_URL` | optional | advisory only; unused by any path |
FairEconomy needs **no key**.

## 7. Startup commands
```powershell
py deploy.py --verify
py healthcheck.py
py portfolio_mt5.py --config funded            # SHADOW — safe, places nothing
py -m market_intel.dashboard --symbols EURUSD,XAUUSD
py -m market_intel.web --host 0.0.0.0 --port 8787 --token <secret>
py -m market_intel.reaction_recorder --symbols EURUSD,XAUUSD,NAS100
```
`--demo-limited` is **not** in this list. It requires separate approval.
