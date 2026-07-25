# SYSTEM_STATUS

Generated **2026-07-25 11:39 UTC** by `healthcheck.py` + `startup.py`.
Every value below is live output, not a written claim. Regenerate with:
```
py healthcheck.py
py startup.py
```

## Subsystem status

| subsystem | status | detail |
|--|--|--|
| version | PASS | 2026.07.25 commit a7e5e3aaaed3 branch phase404-live-demo |
| ⚑ files | **PASS** | 18 required files present |
| ⚑ modules | **PASS** | 15 modules import cleanly |
| environment | WARN | set: none | unset: 7 |
| calendar_providers | PASS | active=faireconomy | tested-working: FairEconomy (ForexFactory JSON) |
| contracts | PASS | 7 contracts | demo-eligible: ['portfolio_multisleeve'] | live-eligible: none |
| ⚑ belief_graph | **PASS** | research=0.6133 operational=0.2523 evidence=3 cap=0.35 |
| ⚑ promotion | **PASS** | state=LIMITED_DEMO_APPROVED demo_trades=0 cap=1pos/0.10% | blocking FULL_DEMO_APPROVED: operational_belief 0.2523 < 0.7,demo_trades 0 < 30 |
| ⚑ execution_gate | **PASS** | blocks unknown strategy; guard blocks unarmed submit |
| ⚑ guardian | **PASS** | reachable, currently BLOCK (GUARDIAN_SNAPSHOT_BAD) — fail-closed is correct |
| ⚑ ledger | **PASS** | 0 entries; orphan policy active (block_all=False) |
| ⚑ reconciliation | **PASS** | naked-stop detection works; exit reconciliation NOT implemented |
| ⚑ demo_envelope | **PASS** | position cap + daily cap + halt all enforced |
| broker | SKIP | MetaTrader5 package not available on this machine |
| telegram | WARN | not configured (TELEGRAM_TOKEN/CHAT_ID unset) |
| entry_points | PASS | 4 entry points present |

⚑ = critical. A FAIL here means the platform must not execute.

## Calendar providers

| provider | implemented | configured | tested | active | note |
|--|--|--|--|--|--|
| FairEconomy (ForexFactory JSON) | yes | yes | yes | yes | no key required; 15-min cache; rate-limits |
| FRED | yes | no | — | no | official US macro; NO consensus forecast |
| MT5 Economic Calendar | yes | no | no | no | MetaTrader5 package not importable here |
| Finnhub | yes | no | — | no | economic-calendar endpoint is premium-gated |
| Trading Economics | yes | no | — | no | guest key discontinued (HTTP 410) |
| FXStreet | yes | no | — | no | needs licensed endpoint |
| CSV | yes | no | — | no | operator-supplied fallback |
| Forex Factory (scrape) | yes | no | — | no | DISABLED by default (ToS) |
| TradingView MCP | yes | no | — | no | advisory only; MT5 authoritative; NOT wired into any path |

## Live diagnostics

| field | value |
|--|--|
| version | 2026.07.25 @ a7e5e3aaaed3 (phase404-live-demo) |
| deployment | MODIFIED 33 files ok, 1 modified |
| modules | 6/6 core modules import |
| providers_configured | FairEconomy(no-key) |
| calendar_active | faireconomy: 71 events, 53 with forecast |
| belief | research 0.6133 | operational 0.2523 | evidence 3 |
| promotion | LIMITED_DEMO_APPROVED | demo_trades 0 | caps 1pos/0.10% | blocking FULL_DEMO_APPROVED:operational_belief 0.2523 < 0.7,demo_trades 0 < 30 |
| guardian | BLOCK (GUARDIAN_SNAPSHOT_BAD) |
| telegram | not configured |
| broker | MetaTrader5 package not available on this machine |

## Governance (immutable)

| bar | value | current |
|--|--|--|
| LIVE research | 0.60 | 0.6133 ✅ |
| LIVE operational | 0.85 | 0.2523 ❌ |
| LIVE demo trades | 100 | 0 ❌ |
| exec→research cap | 0.35 log-odds | enforced |

**No threshold was modified during the reliability work.** `healthcheck.py` fails outright if the
LIVE research bar is not exactly 0.60.

## Known gaps (see ARCHITECTURE_STATE_2026.md)

1. Exit reconciliation not implemented — `exit_verified` is permanently False (HIGH)
2. Zero live fills ever executed — all safety proofs are mock-based (HIGH)
3. Telegram implemented but no runner emits alerts (MEDIUM)
4. Two belief stores: v1 (`--live`) and v2 (`--demo-limited`) not reconciled (MEDIUM)
5. `engine.scan()` has no scheduled runner — opportunities not generated in production (MEDIUM)