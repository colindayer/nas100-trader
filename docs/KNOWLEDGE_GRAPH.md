# TRADING OS KNOWLEDGE GRAPH

_2026-07-13. Documentation only -- no production/strategy/research change. A single
map of every strategy and the evidence around it. Machine-readable twin:
`knowledge_graph.json`. Authoritative status lives in the linked docs; this is the
index that connects them._

Legend -- **Validation** (does live match its evidence): YES / PARTIAL / FIXED / INERT.
**Production**: LIVE / LIVE-restricted / off-funded. Window anchor 2026-07-14, committee 2026-08-16.

---

## S1 -- Asian Sweep (QQQ)
- **Validation:** YES (assumptions preserved post-parity fix)
- **Production:** LIVE (Alpaca full universe; MT5 restricted). GEX-gated → ~11 trades/yr design
- **Lineage:** in-house liquidity-sweep/ICT concept → master_backtest.py → live_trader.run_s1
- **Assumptions:** Asian session bars exist (18–02 ET); VWAP volume; 16:00 close for EMA50; sweep-and-reclaim of Asian low
- **Caveats:** weekend-hold mildly positive but thin; MT5 restricted universe
- **Open investigations:** none (green)
- **Related experiments:** part_a_universe (ETF expansion shadow), weekend_exposure_test
- **Rejected alternatives:** DIX regime filter (EXP-20260710-01), ATR compression gate
- **Evidence docs:** LIVE_TRADING_PARITY, STRATEGY_VALIDATION_AUDIT, WEEKEND_EXPOSURE_AUDIT, SETUP_SUPPLY_ANALYSIS
- **Dashboard:** STRATEGIES, SHADOW (S1_* survivor streams)
- **Obsidian:** vault/03-Validated-Strategies/S1 Asian Sweep.md

## S2 -- Gold FVG (GLD)
- **Validation:** FIXED 2026-07-12 (was INERT — hourly-FVG fired 0/75d; ported to validated daily-FVG lineage)
- **Production:** LIVE. Own evidence clock restarted 2026-07-14 (triggered global clock reset, commit 614e1ba)
- **Lineage:** ICT FVG concept → full_yearly.py daily-FVG → live_trader.run_s2 (daily FVG_Up + green + SPY-bull, long-only, 1.2%/2:1)
- **Assumptions:** overnight GAPS on DAILY bars (unsatisfiable on hourly — the original defect); SPY-bull regime
- **Caveats:** gold weekend gaps are geopolitically driven — NOT generalized from the QQQ weekend audit
- **Open investigations:** first live S2 fill pending (~16/yr expected); weekend behavior unmeasured
- **Related experiments:** none direct
- **Rejected alternatives:** hourly-London-FVG variant (self-superseded)
- **Evidence docs:** STRATEGY_VALIDATION_AUDIT, FINDINGS (S2 inert + S2 fixed entries), CLOCK_RESETS
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/S2 Gold FVG.md

## S3 -- Abnormal Volume (QQQ)
- **Validation:** PARTIAL — provenance drift. Live rule (z>1.5 + ret>1%) is a strict SUBSET of the validated rule (vol>1.3×MA20 + green): ~4/yr vs ~15/yr, 97% overlap
- **Production:** LIVE (Alpaca-only exit path: 5-day time exit / 2% stop; treat MT5 as no-time-exit)
- **Lineage:** in-house volume-surge continuation → validated variant diverged un-reviewed → live z-score variant
- **Assumptions:** daily volume surge + green close; 5-day hold
- **Caveats:** MT5 has no time exit/target; harmed by weekend exposure (force-close flips PF 1.03→1.24)
- **Open investigations:** revert-or-revalidate decision — DEFERRED to 2026-08-16 committee (human 2026-07-13: keep as-is, safe subset)
- **Related experiments:** weekend_exposure_test
- **Rejected alternatives:** —
- **Evidence docs:** S3_VALIDATION_REVIEW, STRATEGY_VALIDATION_AUDIT (decision log), WEEKEND_EXPOSURE_AUDIT
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/S3 Abnormal Volume.md

## S4 -- Multi-Sweep (QQQ + SPY)
- **Validation:** YES (S1 + EMA200 regime; same bracket archetype as S1)
- **Production:** LIVE
- **Lineage:** S1 extended with cross-index confirmation → master_backtest.py → run_s4
- **Assumptions:** as S1, plus 200d EMA regime and dual-index sweep
- **Caveats:** weekend-hold benefit inferred from S1/S5 archetype, not measured standalone
- **Open investigations:** none
- **Related experiments:** weekend_exposure_test (archetype)
- **Rejected alternatives:** —
- **Evidence docs:** LIVE_TRADING_PARITY, STRATEGY_VALIDATION_AUDIT
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/S4 Multi Sweep.md

## S5 -- Opening Range Breakout (QQQ, long/short)
- **Validation:** PARTIAL on CFD — ETF premise intact; on NAS100 CFD the 9:00 ET bar is not an auction open (23h continuous market)
- **Production:** LIVE (10–13 ET window; bracket 1%/3:1)
- **Lineage:** Zarattini/Aziz/Barbon ORB (SSRN 2023/24) → validated hourly-approx → run_s5
- **Assumptions:** a 9:00 bar approximating the opening range; opening-auction structure (ETF-true, CFD-weak)
- **Caveats:** same-day re-entry divergence QUANTIFIED & ACCEPTED (12 extra trades/7.5y, breakeven); **benefits from weekend exposure** (Sharpe .88 vs .72) but carries the book's largest weekend gap tail (−4.09% eq worst, 0/373 breaches)
- **Open investigations:** CFD-vs-ETF S5 execution comparison at month-end (via fills)
- **Related experiments:** vix_ts_gate_test (gate on S1+S5), weekend_exposure_test, S5 re-entry replay
- **Rejected alternatives:** ATR compression pre-filter
- **Evidence docs:** S5_REENTRY_REVIEW, VIX_TERM_STRUCTURE (vix_term_structure_gate), WEEKEND_EXPOSURE_AUDIT, STRATEGY_VALIDATION_AUDIT, LIVE_RESEARCH_DRIFT
- **Dashboard:** STRATEGIES, SHADOW (S5_* streams)
- **Obsidian:** vault/03-Validated-Strategies/S5 ORB.md

## OVN -- Overnight Drift (QQQ)
- **Validation:** YES (enter near close, exit at open; 5% catastrophe stop is additive)
- **Production:** LIVE (30-min overnight task)
- **Lineage:** overnight-return literature → in-house calendar variant → run overnight
- **Assumptions:** overnight drift captured close→open; crosses weekend only on Friday entries
- **Caveats:** over-buy era bug fixed; not a weekend-gap strategy by design
- **Open investigations:** none
- **Rejected alternatives:** RFS/overnight momentum tradeable variant (OVERNIGHT_MOMENTUM_REVIEW — REJECT, CFD-dead)
- **Evidence docs:** OVERNIGHT_MOMENTUM_REVIEW, LIVE_TRADE_REVIEW
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/Overnight Drift.md

## BTC Sweep (BTCUSD, MT5/Pepperstone)
- **Validation:** PARTIAL — venue swap: validated on Binance spot, traded on Pepperstone CFD (basis/spread differ)
- **Production:** LIVE (state-machine + bracket + reconcile guard)
- **Lineage:** S1 ported to crypto → run btc
- **Assumptions:** 24/7 continuous market; UTC sessions
- **Caveats:** venue-swap cost unquantified; reconcile guard prevents accidental shorts
- **Open investigations:** month-end MT5-fills vs Binance-expectation comparison
- **Rejected alternatives:** —
- **Evidence docs:** STRATEGY_VALIDATION_AUDIT, LIVE_TRADE_REVIEW
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/BTC Sweep.md

## BTCTREND / XSMOM (crypto trend + cross-sectional momentum)
- **Validation:** YES on daily rules; but rebalance-managed with NO broker-side stop
- **Production:** LIVE — **keep OFF funded accounts** (no hard stop)
- **Lineage:** Moskowitz/Ooi/Pedersen 2012 TSMOM + Donchian → daily rebalance
- **Assumptions:** daily closes; 24/7
- **Caveats:** no broker stop (rebalance-managed); "force-close Friday" is meaningless (24/7, continuous financing) — out of weekend-audit scope
- **Open investigations:** slow-sleeve economics (Part C) — WAITING post-window
- **Rejected alternatives:** industry-rotation TSMOM (CFD-financing-dead), funding carry (tail risk)
- **Evidence docs:** part_c_tsmom, RESEARCH_GRAVEYARD_AUDIT, TENSORTRADE_EVALUATION
- **Dashboard:** STRATEGIES
- **Obsidian:** vault/03-Validated-Strategies/BTC Trend.md

---

## Cross-cutting evidence & governance
- **Single source of truth:** MONTH_1_LIVE_REPORT / MONTHLY_EVIDENCE_COMMITTEE (committee 2026-08-16)
- **Parity vs validation:** LIVE_TRADING_PARITY (code matches itself) vs STRATEGY_VALIDATION_AUDIT (code matches its evidence) — the audit found S2/S3/S5-CFD/BTC drift parity missed
- **Governance:** CLOCK_RESETS (reset #1: 07-14 by S2 fix), NEXT_30_DAY_MONITORING_PLAN, PROP_READINESS, RESEARCH_BACKLOG (frozen)
- **Graveyard:** RESEARCH_GRAVEYARD_AUDIT + FINDINGS — DIX, ATR compression, RFS/overnight momentum, industry rotation, funding carry, hourly-S2
- **Shadow:** ETF_FORWARD_SHADOW_REVIEW (9 survivor streams), vix_ts_gate_REVIEW (WAITING on backwardation)
- **Ops:** VPS_UPDATE_FIX, STARTUP_FIX_REPORT, DAILY_OPS_REPORT
- **Dashboard pages:** HOME, STRATEGIES, SHADOW, RESEARCH, GRAVEYARD, EXECUTION, EVIDENCE, LOGS, SETTINGS (dashboard/app.py)
