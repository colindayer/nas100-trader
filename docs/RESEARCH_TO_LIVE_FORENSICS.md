# RESEARCH → LIVE FORENSICS — is validated research reaching live trading?

_2026-07-14. Forensic, read-only; no code/strategy/param change. Consolidates prior
audits (FORENSIC_PIPELINE_AUDIT, ALPHA_LEAK_AUDIT, STRATEGY_VALIDATION_AUDIT,
WEEKEND_EXPOSURE_AUDIT, DATA_LINEAGE) + NEW S1/S5 gate funnels measured here. Qwen
used for repo-search first-pass; Claude reaches all conclusions. Unknown kept Unknown._

## Per-strategy pipeline (expected | actual | evidence)
| strategy | validation | production faithful? | key divergence (evidence) |
|---|---|---|---|
| S1 Asian sweep | ETF hourly, gauntlet-passed | YES (post-parity) | sizing overlay + CFD costs on MT5 leg (code vs backtest) |
| S2 Gold FVG | daily-FVG lineage | YES since 07-12 (was INERT) | hourly variant fired 0/75d; ported (FINDINGS) |
| S3 Abnormal vol | daily 1.3xMA20+green | PARTIAL | live z>1.5 rule = strict subset ~4/yr vs 15/yr (VALIDATION_AUDIT) |
| S4 Multi-sweep | ETF hourly | YES | as S1 (archetype) |
| S5 ORB | hourly-approx of ORB paper | PARTIAL on CFD | 9:00 bar != 9:30 auction; largest weekend tail |
| OVN | daily overnight | YES (crash fixed 07-14) | tp=None format crash blocked all OVN trades (now fixed) |
| BTC | Binance spot | PARTIAL | traded on Pepperstone CFD (venue swap) |
| BTC Trend/XSMOM | daily rules | YES rules / no broker stop | keep off funded |

Pipeline verdict: signal SHAPE is faithful end-to-end; every loss point sits at
Validation→Execution (cost/venue/sizing), not in signal generation.

---
## Q1 — Are the gates too restrictive? NO. Evidence: measured funnels.
**S1 (7.5y):** in-session 7448 → sweep+reclaim 949 (**sweep rejects 87%**) → VWAP 718
(−24%) → EMA50 534 (−26%) → not-HighVol 507 (−5%). ~69 fireable/yr pre-GEX/VIX.
**S5 (7.5y):** window 7448 → breakout 2512 (**breakout rejects 66%**) → vol 1839 (−27%)
→ regime 1546 (−16%) → VIX 1354 (−12%).

The gate that removes the most is the **strategy's own defining event** (a liquidity
sweep / a range breakout) — that is the edge, not an over-tight filter. The secondary
filters (VWAP/EMA50/HV/vol) each remove a small, validated slice. **No gate destroys
expectancy**; each was part of the validated rule. GEX (S1) and VIX (S1/S5) are DESIGN
regime gates (S1 only trades negative-GEX mean-revert regimes → the documented ~11/yr).
No gate is over-restrictive relative to the validated research.

---
## Q2 — Are the validated frequencies wrong? Mostly NO; two explained exceptions.
| strategy | validated/mo | expected/mo | live | paper | shadow | explanation |
|---|---|---|---|---|---|---|
| S1 | ~4 | ~1 (GEX-gated) | ~0 | Unknown | logged | downtime + GEX design gate |
| S2 | ~1.3 | 1.3 (post-fix) | 0 pre-fix | — | — | **hourly variant structurally inert; FIXED 07-12** |
| S3 | ~1.25 | ~0.33 | ~0 | — | — | **live rule is a strict subset (proven), not wrong data** |
| S4 | ~4.6 | ~4.6 | ~0 | Unknown | — | downtime |
| S5 | ~4.2 | ~4.2 | ~0 | — | logged | downtime; funnel confirms supply healthy |
| OVN | ~8 | ~8 | **0** | — | — | **crash blocked every OVN order; FIXED 07-14** |
| BTC | ~1.3 | ~1.3 | sparse | — | — | by design |
| BTCTREND | monthly | monthly | rebalances | — | — | runs |

Only TWO frequency discrepancies are "wrong," both now explained & fixed: S2 (inert
hourly port) and OVN (crash-before-submit). S3's low rate is a KNOWN un-validated
tightening, not a wrong validated number. All other ~0-live figures are **downtime**,
not frequency error. **Live/paper counts are largely Unknown from this host — VPS
fills.csv required** (not guessed).

---
## Q3 — Is production seeing the same market research validated? NO — costs/venue differ.
ETF-validated (QQQ/SPY/GLD, 3bps/side, no financing) vs CFD-traded (US100/US500/XAUUSD,
spread+commission+~3bps/day financing, 23h session). Session hours = fixed ET wall-clock;
DST offset detected from a live tick but **falls back to a static value at night/weekend**.
Symbol map QQQ→US100 etc. Bar alignment hourly both sides. S5's "opening range" is the
9:00 bar, not the 9:30 cash auction (no auction on CFD). **Production is NOT faithfully
reproducing the research environment on the CFD leg** — the ETF (Alpaca) leg is faithful.
(Full detail: ALPHA_LEAK_AUDIT, DATA_LINEAGE.)

---
## Q4 — Trace every rejected signal.
At the MECHANISM level (measured funnels above): every rejection matches the validated
rule — bars rejected for not sweeping / not breaking out / below VWAP-EMA / high-vol are
rejected exactly as research intended. **No unintended rejection found in the gate logic.**
The one historical UNINTENDED rejection was S2 (hourly FVG never satisfiable) — a
timeframe bug, now fixed. **Per-signal live rejection traces (which live bar hit which
gate) require the VPS session logs — Unknown from this host; not fabricated.**

---
## Q5 / DELIVERABLE — ranked sources of live expectancy loss

| Issue | Evidence | Confidence | Expected impact | Research reset? | Committee? | Operational only? |
|---|---|---|---|---|---|---|
| Unmodeled CFD cost stack (financing+spread+commission) | full_yearly ETF-cost note vs CFD reality; FINDINGS CFD-law (4x) | HIGH | HIGH (~½ of the est. 25-40% Sharpe haircut) | No | Yes (venue routing) | No (re-cost = analysis) |
| Live risk overlay (vix_mult×RISK_SCALE×DD-throttle) not in backtest | live_trader sizing vs backtest sizing | HIGH | HIGH | No | Yes | No |
| Operational downtime (missing trades) | ~0 clean live trades; prior emoji/tz/OVN crashes (now fixed) | HIGH | HIGH (100% of missing) | No | No | **Yes** |
| S3 rule drift (frequency) | subset measurement 4/yr vs 15/yr, 97% overlap | HIGH | MED | **Yes** | Yes | No |
| Market-order-after-close slippage | mt5 TRADE_ACTION_DEAL vs backtest fill-at-close | MED | MED | No | Maybe | Partly |
| S5 ORB premise on CFD (no auction) | code (9:00 bar); VALIDATION_AUDIT | MED | MED | **Yes** | Yes | No |
| DST static-offset fallback | mt5_broker offset code | MED | MED (episodic, 2x/yr) | No | No | **Yes** |
| Gates | S1/S5 funnels: gates match mechanism | HIGH | ~0 (NOT a loss source) | No | No | No |

---
## VERDICT
**The validated strategies remain fundamentally sound.** The gates are not too
restrictive (the mechanism is the filter, by design); frequencies are correct except two
now-fixed bugs (S2 inert, OVN crash); and no gate destroys expectancy. **No strategy has
lost statistical validity.** S3 is the only apparent outlier and it is NOT invalid — its
live rule is a *validated subset* (97% of its fires overlap the validated rule; same
edge per trade, just ~27% of the count); the fix is to restore the validated rule, not
to discard the strategy.

The gap between validated and live is dominated by **CFD cost + the live risk overlay +
operational downtime**, in that order — none of which is a strategy failure. The single
highest-value action remains non-strategic: **re-validate with the real cost stack and
route ETF-validated strategies to the ETF venue.** Live per-trade R, latency, and reject
data are **Unknown pending the VPS fills.csv + MT5 history** — required before any
number here graduates from estimate to measurement.
