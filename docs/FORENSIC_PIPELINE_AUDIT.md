# FORENSIC PIPELINE AUDIT — research → live faithfulness

_2026-07-14. Feature development halted. Objective: maximize confidence that validated
research reaches live trading intact. Read-only; no code/strategy change. Consolidates
and does NOT re-derive prior audits (ALPHA_LEAK_AUDIT, STRATEGY_VALIDATION_AUDIT,
FORENSIC_INVESTIGATION, WEEKEND_EXPOSURE_AUDIT, DATA_LINEAGE, S5 gate funnel, OVN crash
fix). Claude is final reviewer and sole author of production recommendations. Local
specialists (qwen via ollama — verified) were NOT fanned out: the reading corpus is
already in-context, so delegating it would be the duplicated work this brief forbids._

---
## PHASE 1 — TRADE PIPELINE (every transformation, nothing assumed)

| stage | what happens | where | transformation / loss point |
|---|---|---|---|
| Research | idea/paper → hypothesis | research/ideas,papers | none (firewalled from live) |
| Validation | gauntlet: IS/OOS walk-fwd, 3bps/side, OOS Sharpe>0.5, |corr|<0.3, 6/6 split | master_backtest.py, full_yearly.py | **costs modeled as ETF (3bps), no financing/throttle** |
| Backtest | fill at signal-bar CLOSE, 1 entry/day guard | *_backtest.py | fills at close ≠ live market-order-next-tick |
| Shadow | forward-log would-be signals, NO orders | scripts/research/shadow_etf.py → shadow_signals.csv | ETF-only; 9 survivor streams |
| Production signal | run_s1..s5/ovn/btc recompute the gate chain on broker bars | live_trader.py | hourly bars; session hours = fixed ET wall-clock |
| Risk filters | vix_mult (regime), RISK_SCALE (venue), DD-throttle, daily/monthly kill | live_trader.py prologue | **overlay ABSENT from validated backtest** — changes size & frequency |
| Broker | place_order_safe → MT5 TRADE_ACTION_DEAL (market) / Alpaca bracket GTC | broker.py, mt5_broker.py, alpaca_broker.py | market order; symbol map QQQ→US100 etc; RESTRICTED_UNIVERSE |
| Execution | fill at next tick + spread; MT5 atomic SL/TP | broker adapters | spread+slippage+financing (CFD) not in backtest |
| Telegram | FILL/CRASH/kill alerts; once-daily heartbeat 17:00 ET | alerts.py | log-only (OVN format crash FIXED 2026-07-14) |
| Dashboard | reads fills.csv/ledger/shadow, never recomputes | dashboard/app.py | presentation only |
| Evidence | fills.csv + daily ledger + ops verdict → committee | fill_ledger.py, evidence_report.py | single source of truth |

**Pipeline verdict:** signal SHAPE is faithful end-to-end; the loss points are all at
Validation→Execution — the validated numbers were costed for a venue (ETF) and a sizing
(no throttle) the live path does not use.

---
## PHASE 2 — SIGNAL AUDIT (explanation for every missing trade)

| strategy | exp freq | obs (live) | why the gap — exact cause |
|---|---|---|---|
| S1 | ~47/yr bar; ~11/yr GEX-gated | ~0 clean | operational downtime + GEX gate (by design) + venue throttle |
| S2 | ~16/yr (daily-FVG) | 0 pre-fix | **hourly-FVG fired 0/75d (structurally inert); FIXED→daily 07-12; clock from 07-14** |
| S3 | ~15/yr validated | ~4/yr | **live rule z>1.5&ret>1% ⊂ validated 1.3×MA20&green — 73% of signals never fire** |
| S4 | ~55/yr bar | ~0 | as S1 (downtime + throttle) |
| S5 | ~50/yr | ~0/3-shadow | breakout gate rejects 66% (mechanism, not bug — funnel proven); downtime |
| OVN | ~2/wk | **0 (never traded)** | **place_order_safe crashed on tp=None BEFORE submit — FIXED 2026-07-14** |
| BTC | ~10-20/yr | sparse | by design; venue-swap fills unmeasured |
| BTCTREND | monthly | rebalances | runs; no broker stop |

**Gate funnel (S5, evidence):** window 7448 → breakout 2512 (−4936) → vol 1839 (−673) →
regime 1546 (−293) → VIX 1354 (−192). **Gates are NOT over-rejecting.** Dedup =
per-session lock+cooldown (`_check_and_set_lock`) + `open_syms` check. Symbol map
QQQ→US100/SPY→US500/GLD→XAUUSD/BTC→BTCUSD. DST: offset detected from a live tick each
run, **static config fallback (=3h) when no fresh tick (night/weekend)** = the fragility.

**Every missing trade explained:** downtime (S1/S4/S5), inert-code (S2, fixed),
rule-drift (S3), crash-before-submit (OVN, fixed), by-design gating (GEX, VIX,
one-per-day). No unexplained missing trades.

---
## PHASE 3 — PARITY AUDIT (difference → expected impact)
Full ranked detail in ALPHA_LEAK_AUDIT.md. Summary of expectancy-changing differences:

| difference | validated | production | est. impact | conf |
|---|---|---|---|---|
| instrument | ETF (QQQ/SPY/GLD) | CFD (US100/US500/XAUUSD) | −0.05…−0.15 R | MED |
| session | cash hours | 23h continuous | S5 ORB premise weak | MED |
| financing | none | ~3bps/day ×3 wknd | −0.06…−0.10 R | HIGH |
| fill | signal-bar close | market next tick + spread | −0.02…−0.05 R | MED |
| sizing | raw risk/stop | ×vix_mult×RISK_SCALE×DD-throttle | −0.05…−0.20 R + freq | HIGH |
| commission | 0 (ETF) | ~$3.5/lot (CFD) | −0.005…−0.02 R | MED |
| stop/target | as validated | atomic MT5 bracket (faithful) | ~0 | HIGH |
| clock resets | n/a | reset #1 07-14 (S2 fix) | bookkeeping | HIGH |
| config drift | — | none found | 0 | HIGH |

**Aggregate:** ~25–40% Sharpe haircut from the CFD-cost + throttle stack before any
strategy is "wrong."

---
## PHASE 4 — EXECUTION AUDIT (measured vs required-but-missing)

| metric | status | evidence / gap |
|---|---|---|
| expected trades | modeled (per strategy above) | HIGH |
| actual trades | **~0 clean** | window just anchored 07-14; prior downtime |
| expected R | +0.20…+0.43 (audits) | HIGH |
| actual R | **INSUFFICIENT DATA** | no live fills; fills.csv empty on this host |
| execution latency | **NOT MEASURED** | needs VPS fills.csv (signal_ts vs fill ts) |
| broker rejects / timeouts / order failures | **NOT VISIBLE from Mac** | on VPS logs; place_order_safe retries 3× |
| Telegram failures | none known; OVN alert crash FIXED | broker.py |
| dashboard inconsistencies | none (read-only, VPS cells honest UNKNOWN) | verified |
| GitHub Action failures | historic (emoji/timezone) FIXED | STARTUP_FIX_REPORT |
| VPS failures | nas100-update 0x800710E0 FIXED 07-13 (Last Result 0) | VPS_UPDATE_FIX |

**INSUFFICIENT EVIDENCE — required additional data (do not guess):**
1. **VPS `logs/fills.csv`** — the only source of actual R, slippage, latency, rejects.
2. **MT5 trade-history export** (Toolbox→Report) — closed-trade R for bracket exits.
3. **VPS `logs/mt5_*.log`** — broker rejects/timeouts per session.
Until these are merged, Phase-4 live metrics are UNKNOWN, not zero.

---
## PHASE 5 — RANKED FIXES (one table; prefer one verified fix over ten ideas)

| # | fix | sev | conf | est. impact | complexity | changes research? | new validation cycle? | resets clock? |
|---|---|---|---|---|---|---|---|---|
| 1 | **Re-validate all strategies with REAL cost stack** (CFD financing/spread/comm; ETF costs on Alpaca) | HIGH | HIGH | reframes every committee number; 0 risk | low | no | no (re-costs existing) | **NO** |
| 2 | **Merge VPS fills.csv + MT5 history** into evidence | HIGH | HIGH | turns Phase-4 UNKNOWN→measured | low | no | no | NO |
| 3 | **Route ETF-validated strategies to Alpaca ETF venue** (S1/S3/S4/S5 on QQQ/SPY) | HIGH | HIGH | removes financing + instrument mismatch | low-med | no | no | NO (routing, not signal) |
| 4 | **Restore S3 validated rule** (revert z-score tightening) | MED | HIGH | +73% S3 frequency | low | no (restores it) | re-confirm only | **YES** |
| 5 | **OVN crash fix** (tp=None format) | HIGH | HIGH | OVN can trade at all | done | no | no | operational — NO |
| 6 | **Harden MT5 DST fallback** (DST-aware, not static 3h) | MED | MED | removes twice-yearly wrong-window leak | low | no | no | NO (infra) |
| 7 | **Fix S5 ORB def (9:30) or retire on CFD** | MED | MED | large if premise weak | med | yes (signal) | **YES** | **YES** |
| 8 | Give S3-MT5 / BTCTREND broker-side exits | MED | HIGH | caps tail risk | med | yes | YES | YES |
| 9 | Promote VIX-term-structure gate (in shadow) | LOW | MED | +Sharpe if stress episode confirms | med | yes | YES | YES |

**Recommendation:** execute #1, #2, #3, #5 (all zero/low-risk, no clock reset, no new
validation) BEFORE anything that touches signals. #4/#6/#7/#8/#9 are committee-gated,
post-window. **No feature development is justified** — restoring parity has strictly
higher expected value than any new alpha, and the validated strategies are not exhausted
(healthy setup supply, real risk-on edge — FORENSIC_INVESTIGATION).

---
## SUCCESS CRITERIA
- ✓ every strategy traced end-to-end (Phase 1)
- ✓ every rejected/missing trade explained (Phase 2 — none unexplained)
- ✓ every implementation difference documented (Phase 3 + ALPHA_LEAK_AUDIT)
- ⚠ live expectancy loss quantified as ESTIMATES; **actual R/latency/rejects require VPS
  fills.csv + MT5 history** (Phase 4 — explicitly stated, not guessed)
- ✓ every fix has governance columns (Phase 5)
