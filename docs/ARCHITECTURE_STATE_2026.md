# ARCHITECTURE_STATE_2026

Audit date **2026-07-25**. Derived by inspecting the repository, not by trusting prior reports.
Where an earlier document and the code disagree, **the code is reported**.

---

## 1. SYSTEM OVERVIEW

```
                 ┌─────────────── RESEARCH SIDE (~/research-lab) ───────────────┐
                 │  event DB · walk-forward · scorecard · inference · portfolio  │
                 │  FIREWALL: research never imports production                  │
                 └──────────────────────────┬────────────────────────────────────┘
                                            │ exported artifact (belief JSON)
                                            ▼
MARKET DATA (MT5)  ─┐
CALENDAR (5 chain) ─┼─► market_intel/state.py ─► engine.py ─► opportunity.py ─┐
TRADINGVIEW (opt)  ─┘        (classify)          (pre/post)     (registry)    │
                                                                              ▼
                                                      execution_safety/gate.py::authorize()
                                        ┌───────────────────────┼───────────────────────┐
                                        ▼                       ▼                       ▼
                            strategy_contract.py     promotion_pipeline_v2.py     guardian_bridge.py
                            (contract/version/       (5 states, caps)             (prop_risk_guardian)
                             trial/symbol)                     │
                                        └───────────────────────┼───────────────────────┘
                                                                ▼
                                                    OrderIntent  ──► position_ledger.py (BEFORE submit)
                                                                ▼
                                                    execution_guard.py::armed()  (one-shot token)
                                                                ▼
                                                    mt5_broker / portfolio_mt5 order_send (+ broker SL)
                                                                ▼
                                                    broker_reconciliation.py::reconcile()
                                                                ▼
                                                    operational_belief.py ─► belief_graph_v2.py
                                                                            (OperationalBelief only)
```

Communication is **in-process Python imports**; there is no message bus, queue, or RPC. State is
exchanged through JSON/JSONL files under `registry/`.

---

## 2. MODULE INVENTORY

### execution_safety/ (governance + execution)
| file | lines | responsibility | status | key deps |
|--|--|--|--|--|
| `gate.py` | 134 | fail-closed `authorize()`; OrderIntent | **production-ready** | strategy_contract |
| `strategy_contract.py` | 74 | contract schema + registry | **production-ready** | — |
| `execution_guard.py` | 49 | one-shot arming token at broker boundary | **production-ready** | — |
| `belief_graph_v2.py` | 110 | two independent beliefs, evidence classes, exec cap | **production-ready** | — |
| `promotion_pipeline_v2.py` | 63 | 5 promotion states + caps | **production-ready** | belief_graph_v2 |
| `operational_belief.py` | 79 | per-trade execution quality → evidence | **production-ready** | belief_graph_v2 |
| `demo_evidence.py` | 48 | limited-demo envelope + evidence write | **production-ready** | belief_graph_v2, promotion_v2 |
| `position_ledger.py` | 69 | append-only ledger, orphan classification | **partial** — wired in demo path only |
| `broker_reconciliation.py` | 50 | post-fill reconcile, naked-stop detection | **partial** — no exit-side reconcile |
| `guardian_bridge.py` | 36 | calls prop_risk_guardian, fail-closed | **production-ready** | scripts/prop_risk_guardian |
| `belief_reader.py` | 51 | legacy v1 belief snapshot reader | **deprecated** — superseded by v2, still used by `--live` |
| `promotion_gate.py` | 43 | v1 promotion rule | **deprecated** — superseded by promotion_pipeline_v2 |
| `belief_feedback.py` | 80 | realised P&L → v1 belief | **partial/unused** — v1 store; not called by any runner |
| `prop_objective.py` | 63 | firm configs + survival check | **unused** — not called by any execution path |
| `shadow.py` | 47 | shadow step + parity replay | **partial** — used in tests/audit only |
| `gsr_strategy.py` | 31 | GSR signal emitter | **unused** — no runner invokes it |
| `strategy_registry_shim.py` | 3 | test helper | test-only |
| `test_*.py` (6 files) | 476 | governance test suites | **production-ready** |

### market_intel/ (observation, cannot trade)
| file | lines | responsibility | status |
|--|--|--|--|
| `state.py` | 112 | market classification (trend/vol/session/kill zones/structure/FVG/OB/VWAP) | **production-ready** |
| `faireconomy_provider.py` | 197 | ForexFactory published JSON feed, cache, retry, diagnose | **production-ready** |
| `calendar_provider.py` | 161 | 8-provider chain + EconomicEvent + history | **production-ready** |
| `calendar_feed.py` | 182 | legacy feed used by dashboards; delegates to faireconomy/FRED | **production-ready** |
| `fred_provider.py` | 94 | FRED official US macro (no forecasts) | **production-ready** |
| `web.py` | 221 | HTML dashboard, token auth, host bind | **production-ready** |
| `dashboard.py` | 108 | text dashboard | **production-ready** |
| `engine.py` | 74 | pre-event reports, post-Actual opportunities, routes to gate | **partial** — not invoked by any scheduled runner |
| `opportunity.py` | 105 | Opportunity + append-only registry | **partial** — populated only via `engine.scan()` |
| `reaction_recorder.py` | 125 | records post-release market moves | **production-ready** — **standalone, no callers** |
| `telegram_notifier.py` | 89 | 9 alert classes | **implemented, NOT INTEGRATED** — **no callers** |
| `tradingview_bridge.py` | 46 | optional MCP + MT5 fallback | **stub-quality** — never invoked by any path |
| `calendar_diag.py` | 34 | provider diagnostics | utility |

### scripts/
| file | lines | status |
|--|--|--|
| `portfolio_mt5.py` | 518 | **production-ready** — shadow, `--live`, `--demo-limited` |
| `prop_risk_guardian.py` | 322 | **production-ready** — standalone risk supervisor |
| `phase404_live.py` | 234 | **deprecated** — research-rejected strategy (−0.80R) |

---

## 3. EXECUTION PIPELINE — actual transitions

| # | transition | performed by | status |
|--|--|--|--|
| 1 | Market Data → bars | `portfolio_mt5.fetch_daily()` / `state.classify()` via `mt5.copy_rates_from_pos` | ✅ |
| 2 | Calendar → events | `calendar_feed.load()` → `from_faireconomy_late()` → `faireconomy_provider.load()` | ✅ |
| 3 | TradingView → context | `tradingview_bridge.chart_context()` | ⚠️ **never called** |
| 4 | Data → Market Intelligence | `market_intel.state.classify()` | ✅ |
| 5 | Intelligence → Opportunity | `engine.scan()` → `opportunity.from_release()` | ⚠️ **no scheduled caller** |
| 6 | Opportunity → Belief | `engine.evaluate_through_pipeline()` | ⚠️ fails closed; belief passed in by caller |
| 7 | Belief → Promotion | `promotion_pipeline_v2.evaluate()` | ✅ (demo path) |
| 8 | Promotion → Guardian | `guardian_bridge.guardian_ok()` → `prop_risk_guardian.evaluate()` | ✅ |
| 9 | Guardian → Contract | `gate.authorize()` steps 1–5 | ✅ |
| 10 | Contract → Execution Gate | `gate.authorize()` full chain | ✅ |
| 11 | Gate → Ledger | `PositionLedger.record_intent()` **before** submit | ✅ (demo path) |
| 12 | Ledger → Broker | `execution_guard.armed()` + `mt5.order_send()` with `sl` | ✅ |
| 13 | Broker → Reconciliation | `_capture_execution()` → `broker_reconciliation.reconcile()` | ✅ entry only |
| 14 | Reconciliation → Belief Feedback | `demo_evidence.record()` → `operational_belief.to_evidence()` | ✅ OperationalBelief only |
| 15 | Exit → reconciliation | — | ❌ **NOT IMPLEMENTED** |
| 16 | Realised P&L → ResearchBelief | — | ❌ **NOT IMPLEMENTED** (by design, capped) |

### Verified defect in the demo path
`portfolio_mt5.py:317` passes **`inference=lambda s: "ALLOW_PAPER"`** — a hardcoded constant.
`--demo-limited` checks the **promotion state** (`evaluate()`) but does **not** consult
`belief_reader`/`belief_graph_v2` for the inference decision. The `--live` path (line 442) *does*
pass a real belief decision. **Inconsistent; the demo path is weaker than the legacy path here.**

---

## 4. BELIEF SYSTEM (live values)

```
strategies in graph : ['portfolio_multisleeve']
ResearchBelief      : 0.6133
OperationalBelief   : 0.2523
STATE               : LIMITED_DEMO_APPROVED   (position_cap 1, risk 0.10%)
blocking FULL_DEMO  : operational_belief 0.2523 < 0.70 ; demo_trades 0 < 30
```

| evidence class | → Research | → Operational |
|--|--|--|
| Backtest | 0.60 | 0.00 |
| WalkForward | 1.00 | 0.00 |
| Bootstrap | 0.80 | 0.00 |
| Shadow | 0.00 | 0.50 |
| DemoExecution | 0.10 *(capped)* | 1.00 |
| LiveExecution | 0.15 *(capped)* | 1.00 |

`MAX_EXEC_RESEARCH_LOGODDS = 0.35` — hard ceiling so execution quality cannot accumulate into
edge-confidence. Regression-tested.

| state | research ≥ | ops ≥ | demo trades ≥ |
|--|--|--|--|
| SHADOW_APPROVED | 0.40 | — | 0 |
| LIMITED_DEMO_APPROVED | 0.50 | — | 0 |
| FULL_DEMO_APPROVED | 0.55 | 0.70 | 30 |
| **LIVE_APPROVED** | **0.60** | 0.85 | 100 |

**Two parallel belief systems exist.** v1 (`belief_reader.py` + `registry/belief_graph.json`) is used
by `--live`; v2 (`belief_graph_v2.py` + `registry/belief_v2.json`) by `--demo-limited`. Not reconciled.

---

## 5. MARKET INTELLIGENCE PROVIDERS

| provider | implemented | configured | working | role | notes |
|--|--|--|--|--|--|
| **FairEconomy (ForexFactory JSON)** | ✅ | ✅ no key needed | ✅ **71 events, 53 forecasts** | **PRIMARY** | published feed, not scraping; 15-min cache; retry/backoff; rate-limits |
| **FRED** | ✅ | ✅ `FRED_API_KEY` | ✅ 10 US series | fallback | **no consensus forecast** — cannot produce surprises |
| **MT5 calendar** | ✅ | n/a | ❔ untested | fallback | requires a build exposing `calendar_value_history` |
| **Finnhub** | ✅ | key set | ❌ | fallback | economic-calendar endpoint is premium-gated |
| **Trading Economics** | ✅ | ✗ no key | ❌ | fallback | guest key discontinued (HTTP 410) |
| **FXStreet** | ✅ | ✗ no URL | ❌ | fallback | needs licensed endpoint |
| **CSV** | ✅ | ✗ no file | ❌ | last resort | operator-supplied |
| **Forex Factory (scrape)** | ✅ adapter | ✗ | **DISABLED** | — | off unless `FOREXFACTORY_ENABLED=1` (ToS) |
| **TradingView MCP** | ⚠️ stub | ✗ | **NOT WIRED** | — | `chart_context()` exists; **no code path calls it** |

Chain (`calendar_feed.load`): `faireconomy → api → mt5 → fred → csv`.
Chain (`calendar_provider.PROVIDERS`): `faireconomy, mt5, finnhub, fred, tradingeconomics, fxstreet, forexfactory, csv`.

---

## 6. DASHBOARDS

| dashboard | entry point | purpose | status | missing |
|--|--|--|--|--|
| **Web** | `py -m market_intel.web --host 0.0.0.0 --port 8787 --token X` | browser view: state, calendar, beliefs, promotion, evidence | ✅ working, Mac-accessible | no liquidity map, no FVG/OB overlays, no opportunity queue detail, no system-health pane, no TradingView view |
| **Text** | `py -m market_intel.dashboard --symbols ...` | terminal view | ✅ working | same gaps |
| **Research (Streamlit)** | `dashboard/app.py` (separate repo) | research cockpit | out of scope for this audit | — |

---

## 7. TELEGRAM

- **Implemented:** ✅ `telegram_notifier.py`, 9 alert classes (`opportunity, calendar, guardian_block, promotion, shadow_result, demo_fill, live_fill, daily_summary, critical_error`), confidence filter, append-only log.
- **Configured:** ✅ dashboard reports `TELEGRAM configured` on the VPS.
- **Tested:** ✅ 4 unit tests (unconfigured path, unknown class, confidence filter, cannot-trade).
- **INTEGRATED:** ❌ **No module calls it.** Grep confirms zero callers outside its own tests.
  No fill, guardian block, promotion change, or opportunity currently triggers an alert.
- **Missing:** wiring into `portfolio_mt5` (fills/blocks), `demo_evidence` (defects), promotion
  transitions, daily summary scheduler.

---

## 8. EXECUTION SAFETY VERIFICATION

| control | implemented | enforced where | proof |
|--|--|--|--|
| Guardian veto | ✅ | `guardian_bridge` → `gate.authorize` | `test_guardian_veto_cannot_be_overridden` |
| Authorization chain | ✅ | `gate.authorize()` 10 checks | `test_fail_closed` 14/14 |
| Execution gate / arming | ✅ | `execution_guard.consume_or_block()` one-shot | `test_arming_is_single_use...` |
| Broker-side stops | ✅ | `sl` in every `order_send`, clamped to `trade_stops_level` | code + `test_missing_stop_blocks` |
| Ledger before submit | ✅ | `PositionLedger.record_intent()` | `test_recovery` |
| Reconciliation (entry) | ✅ | `_capture_execution` → `reconcile` | `test_missing_broker_stop_is_critical` |
| Reconciliation (exit) | ❌ | — | **gap** |
| Duplicate detection | ⚠️ partial | `no_duplicate` from position count; one-shot arming | not independently tested against restart |
| Position limits | ✅ | envelope `max_positions` from promotion state | `test_cannot_pyramid_beyond_envelope` |
| Risk limits | ✅ | `risk_cap_pct` from promotion state | `test_risk_cap_is_enforced_by_state` |
| Promotion envelope | ✅ | `LimitedDemoEnvelope` + auto-halt | `test_critical_reconciliation_failure_halts` |
| Legacy path retired | ✅ | guard on `MT5Broker.place_order` | `test_legacy_retired` 3/3 |
| Demo/real guard | ✅ | `account_is_demo` + contract status | `test_real_account_needs_live_approved` |

**Total: 72/72 tests pass** (14+7+3+3+11+11+6+9+8).
**All proofs are against mocks. Zero live fills have ever been executed or reconciled.**

---

## 9. REMAINING GAPS

| # | gap | severity | risk | effort |
|--|--|--|--|--|
| 1 | **Exit reconciliation not implemented** | **HIGH** | `exit_verified` permanently `False` → caps per-trade quality at 0.91 and drags OperationalBelief; exits are unverified | 1–2 days |
| 2 | **`--demo-limited` uses hardcoded `inference="ALLOW_PAPER"`** | **HIGH** | belief graph does not gate the demo path; weaker than `--live` | 1 hour |
| 3 | **Telegram not integrated** | MEDIUM | silent failures; no alert on critical halts | 2–4 hours |
| 4 | **Two parallel belief systems (v1/v2)** | MEDIUM | `--live` and `--demo-limited` consult different stores | 1 day |
| 5 | **`engine.scan()` has no scheduled runner** | MEDIUM | opportunities are never generated in production | 2 hours |
| 6 | **TradingView MCP never invoked** | LOW | advertised capability is inert | 1 day |
| 7 | **`prop_objective.py` unused** | MEDIUM | prop-firm survival never consulted at order time | 4 hours |
| 8 | **`belief_feedback.py` orphaned (v1)** | MEDIUM | realised P&L never re-enters any belief | 4 hours |
| 9 | **No duplicate-order test across restart** | MEDIUM | idempotency unproven | 4 hours |
| 10 | **Zero live-fill validation** | **HIGH** | every safety proof is mock-based | needs market hours |
| 11 | **Dashboard missing liquidity map / FVG-OB overlays / opportunity queue** | LOW | cosmetic | 1 day |
| 12 | **No unified audit index** | LOW | 6 separate JSONL stores | 4 hours |
| 13 | **Challenge Mode (scaling/pyramiding) not started** | LOW | spec item unbuilt | 2 days |
| 14 | **`gsr_strategy.py` unreachable** | LOW | dead code | 1 hour |
| 15 | **No automated deployment** | MEDIUM | manual PowerShell sync; drift caused repeated stale-file failures | 4 hours |

---

## 10. ARCHITECTURE SCORECARD

| subsystem | score | rationale |
|--|--|--|
| **Research** | 8/10 | rigorous, pre-registered, honest negatives; belief graph sound. Loses points: research lives in a separate repo, artifacts hand-exported |
| **Execution** | 7/10 | fail-closed chain, broker stops, ledger, arming all real. Loses points: no exit reconciliation, zero live fills |
| **Market Intelligence** | 6/10 | classification + calendar genuinely work. Loses points: engine unscheduled, TradingView inert, opportunities never generated in prod |
| **Governance** | 9/10 | strongest subsystem: 5 states, dual beliefs, capped leakage, immutable live bar, 72 tests |
| **Monitoring** | 5/10 | two working dashboards; no alerting integration, no health checks, no uptime monitoring |
| **Evidence** | 7/10 | append-only ledgers, evidence classes, recorder running. Loses points: no unified index, feedback loop orphaned |
| **Documentation** | 8/10 | extensive and honest, incl. gap disclosure. Loses points: several docs describe intent rather than current code |
| **Deployment** | 3/10 | manual file-by-file PowerShell; caused repeated stale-file incidents; no versioning check on the VPS |
| **Testing** | 7/10 | 72 tests, structural guarantees, regression coverage. Loses points: 100% mock-based, no integration/live tests |

**Weighted overall: 6.7 / 10**

---

## 11. DEPLOYMENT AUDIT

**Current mechanism: manual PowerShell file-by-file sync from GitHub raw URLs.**

| method | supported | notes |
|--|--|--|
| Git deployment | ❌ | VPS has no clone; no `git pull` workflow |
| ZIP deployment | ❌ | no release artifact |
| Manual copy | ✅ | `docs/VPS_SETUP.md` full-sync block |
| PowerShell sync | ✅ **actual method** | `iwr` per file from raw.githubusercontent |
| Docker / CI | ❌ | none |

**Verified defect:** `raw.githubusercontent.com` caches by path and **ignores `?v=` query strings**.
Cache-busted downloads repeatedly returned stale files, causing multiple debugging cycles.
**Mitigation now in use: SHA-pinned URLs** (`/<commit-sha>/path`), which are immutable.
**There is no version check on the VPS** — nothing detects that a deployed file is out of date.
This is the weakest part of the system and the direct cause of the most operational failures.

---

## 12. FINAL VERDICT

### Maturity: **LIMITED DEMO READY** (with two caveats)

- Beyond *Prototype*: real governance, 72 passing tests, fail-closed authorization, immutable live bar.
- Beyond *Research Platform*: an execution path exists, is gated, ledgered, and reconciled at entry.
- Beyond *Paper Trading Platform*: shadow mode works and has already caught 5 real defects.
- **NOT Full Demo Ready:** exit reconciliation missing (gap 1) and zero live fills validated (gap 10).
- **NOT Live Ready:** requires research ≥ 0.60 (currently 0.6133 ✓), operational ≥ 0.85
  (currently **0.2523**) and **100 clean demo trades (currently 0)**.

### Two caveats on the "Limited Demo Ready" label
1. **Gap 2 must be closed first.** `--demo-limited` currently bypasses the belief graph for its
   inference decision (hardcoded `ALLOW_PAPER`). It is governed by promotion state and Guardian, but
   not by belief. This is a one-hour fix and should precede any demo execution.
2. **Every safety guarantee is mock-proven.** No order has ever been filled by this system. The first
   live fill is an experiment, not a routine operation, and must be manually reviewed.

### Honest summary
Governance is the strongest component and genuinely unusual for a retail system. Deployment is the
weakest and has caused most real-world failures. The research side has produced **one statistically
significant finding** (NFP post-announcement continuation, t = +3.16 / +3.44 over 114 releases) which
is **not yet tradeable-proven** after realistic spreads. No strategy in the repository is approved for
live capital, and the system correctly refuses to place one.
