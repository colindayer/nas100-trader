# FORENSIC INVESTIGATION — faithful expression of validated edge in production

_2026-07-13. Lead investigator: Claude (sole authority for conclusions). Read-only —
no code/strategy/param change. Evidence over opinion: measurements from this repo's
data, cited. Specialized-assistant delegation (Qwen/GLM bridge, subagents) was NOT
used — it would re-derive context already held (the "duplicated work" the brief
forbids); conclusions are mine either way. Builds on ALPHA_LEAK_AUDIT, VALIDATION_AUDIT,
WEEKEND_EXPOSURE_AUDIT, MACRO_REGIME_SURVEY, the VIX-ts gate shadow._

## EXECUTIVE SUMMARY (one page)
**The validated edge is faithfully SHAPED in production but not faithfully COSTED or
CONSISTENTLY RUN.** Three evidence-backed conclusions:

1. **Gates are not over-rejecting.** The S5 funnel shows the breakout gate does 91% of
   the filtering (mechanism); regime gates (bull, VIX<25) reject only 485 of 7448
   window-bars combined. ~183 fireable bar-events/yr survive → ~50 trades/yr. Low live
   frequency is **operational downtime + venue/throttle**, NOT filters eating signals.
   (This reconfirms SETUP_SUPPLY_ANALYSIS with a full funnel.)
2. **The largest expectancy leak is unmodeled cost + live throttle, not bad strategies.**
   The validated numbers were measured on ETF, 3 bps/side, no financing, no throttle.
   Live adds CFD financing, wider spread, market-order slippage, and a `vix_mult ×
   RISK_SCALE × DD-throttle` sizing overlay absent from the backtest — an estimated
   **25–40% Sharpe haircut before any strategy is "wrong."** (ALPHA_LEAK_AUDIT.)
3. **S5's edge is strongly regime-conditional — but that is mostly EXPLANATORY, not yet
   a production filter.** It is a risk-on strategy (VIX<20 avgR +0.93 vs VIX>25 −0.08;
   contango +0.93 vs backwardation −0.43; prior-day-up +2.00 vs −0.75). These are real
   but carry heavy regime-clustering/overfitting risk and need the adversarial battery
   before promotion. Only the VIX-term-structure gate is shadow-validated so far.

**The single highest-EV action is not an alpha idea — it is to re-validate every
strategy with the real cost stack so the committee compares live against an honest
baseline.** One verified production fix (route ETF-validated strategies to the ETF
venue; restore S3's validated rule) beats ten regime-filter ideas. The validated
strategies are NOT exhausted; do not add new strategies.

---

## REPORT 1 — RANKED ALPHA LEAK (per-trade expectancy loss)
Full detail in ALPHA_LEAK_AUDIT.md. Ranked summary:

| rank | leak | Δ expectancy | conf |
|---|---|---|---|
| 1 | live risk overlay (vix_mult×RISK_SCALE×DD-throttle) absent from backtest | −0.05…−0.20 R + freq | HIGH |
| 2 | CFD financing (~3bps/day, ×3 weekend) not in ETF backtest | −0.06…−0.10 R | HIGH |
| 3 | ETF-validated edge traded on CFD (instrument/hours/spread) | −0.05…−0.15 R | MED |
| 4 | S5 ORB = 9:00 hourly bar, not 9:30 cash open / no CFD auction | −0.10…−0.20 R | MED |
| 5 | market-order-after-close vs backtest fill-at-signal-close | −0.02…−0.05 R | MED |
| 6 | S3 rule drift (subset) — see Report 2 (a frequency, not per-trade, leak) | ~0/trade | HIGH |
| 7 | DST/session-boundary fragility on MT5 | episodic | MED |

---

## REPORT 2 — RANKED PRODUCTION GAP (expected vs observed behaviour)

**Evidence — S5 gate funnel (7.5y bar-level):**
```
in 10-13 window        7448
+ close>ORB high       2512   breakout gate rejects 4936  (66% — the mechanism)
+ volume>0.6x ORB      1839   vol gate rejects 673
+ bull regime          1546   regime rejects 293
+ VIX<25 (full)        1354   VIX gate rejects 192
-> ~183 fireable/yr → ~50 trades/yr after one-per-day
```

| rank | gap | expected | observed | root cause (evidence) | conf |
|---|---|---|---|---|---|
| 1 | **operational downtime** | ~50 S5/yr, ~47 S1/yr | ~0 clean live | prior emoji-crash/timezone outages; window only just anchored 07-14 | HIGH |
| 2 | **S3 frequency** | ~15/yr (validated rule) | ~4/yr (live subset) | live rule z>1.5&ret>1% ⊂ validated 1.3×MA20&green — 73% of signals never trade | HIGH |
| 3 | **venue/throttle frequency** | full book | vix_mult=0 drops trades | regime throttle removes trades in stress (by design, but not in the validated count) | HIGH |
| 4 | **S2 (now fixed)** | 0 (was inert) → ~16/yr | pending | hourly-FVG fired 0/75d; ported to daily lineage 07-12 | HIGH |
| 5 | S5 CFD vs ETF fill quality | ETF-equivalent | unmeasured | no auction on CFD; fills.csv will measure | MED |

**Conclusion:** the production gap is dominated by DOWNTIME and S3 rule-drift, both
fixable and measurable — not by gates rejecting valid signals.

---

## REPORT 3 — RANKED REGIME FILTER (S5; explanatory vs predictive)

Single-variable conditioning on 369 S5 trades, avgR base +0.44. All inputs are known
BEFORE entry (prev-close VIX/VIX3M, prior-day return, today's open gap) — no look-ahead.

| variable | in-regime avgR | out avgR | Δ | p | class | overfitting risk |
|---|---|---|---|---|---|---|
| **VIX term structure (contango vs backwardation)** | +0.93 / −0.43 | | +1.42 | <0.001 | **predictive candidate (shadow-validated)** | MED |
| VIX level <20 vs >25 | +0.93 / −0.08 | | +1.0 | <0.001 | explanatory (collinear w/ ts) | MED |
| prior-day up | +2.00 | −0.75 | +2.75 | <0.001 | explanatory — momentum-on-momentum, regime-clustered | HIGH |
| overnight gap up | +1.13 | −0.24 | +1.37 | <0.001 | explanatory — collinear w/ prior-day | HIGH |
| high realized vol | +0.35 | +0.53 | −0.18 | 0.36 | not significant | — |
| month-end (≥25th) | +0.35 | +0.47 | −0.12 | 0.61 | not significant | — |
| Monday / Friday | +0.59 / +0.13 | | ns | 0.50/0.16 | not significant (weak Friday drag) | — |

Not evaluated here (require data not in repo): credit spreads, yield curve, breadth,
earnings concentration, OPEX, liquidity proxies — see MACRO_REGIME_SURVEY for the
qualitative pass; DXY gate is WAITING on its adversarial battery.

**Verdict:** S5 is genuinely risk-on-conditional (explanatory, robust sign). But
prior-day/gap/VIX-level are **collinear and regime-clustered** — as standalone
production filters they are high overfitting risk. **Only the VIX term-structure gate
has survived adversarial review and is in forward shadow.** Everything else is
EXPLANATORY until it passes the same battery. Do not confuse the strong t-stats with
production value.

---

## REPORT 4 — RANKED EXPECTED ROI (recommendations by expected value)

| rank | recommendation | EV rationale | Phase-3 class | provenance preserved | reset? | cost | conf |
|---|---|---|---|---|---|---|---|
| 1 | **Re-validate all strategies with real CFD/ETF cost stack** | reframes every committee number; recovers no edge but stops mis-attributing the haircut; zero risk | Validation only | YES | NO | 1 day | HIGH |
| 2 | **Route ETF-validated strategies (S1/S3/S4/S5) to the Alpaca ETF venue; CFD only where sole venue** | removes financing + instrument mismatch on the validated path | Committee → Production candidate | YES | NO (routing, not signal) | low | HIGH |
| 3 | **Restore S3 validated rule** (revert z-score tightening) | recovers ~73% of S3 frequency; pure parity | Committee → Production candidate | YES | **YES** (signal-touching) | low | HIGH |
| 4 | **Finish the evidence month + export MT5 history** | the only thing that turns estimates into measured live deltas | Documentation/Ops | YES | NO | time | HIGH |
| 5 | **VIX term-structure gate** (already shadowing) | the one regime filter with adversarial support; +Sharpe if a stress episode confirms | Shadow → Committee | YES | YES if promoted | med | MED |
| 6 | **Fix S5 ORB definition (9:30) or retire on CFD** | parity; large if premise is weak | Committee → Production candidate | YES | YES | med | MED |
| 7 | **Harden MT5 DST/session offset** | removes twice-yearly total leak | Validation → Production candidate | YES | NO (infra) | low | MED |
| 8 | prior-day / gap / VIX-level filters | high t-stat but explanatory/overfit; battery first | Research backlog | n/a | n/a | med | LOW |

**Every production candidate above preserves research provenance (they restore or
re-cost the validated lineage; none invents an indicator). Items #3/#6 reset the clock
and are therefore post-window, committee-gated.**

---

## Phase-3 governance summary
- **Documentation only:** this report, #4.
- **Validation only:** #1, #7.
- **Research backlog:** #8 (regime filters beyond VIX-ts).
- **Shadow testing:** #5.
- **Committee discussion:** #2, #3, #6 (all routing/parity, provenance-preserving).
- **Production candidate:** #2, #3, #6, #7 — post-window, clock-aware.

## Are the validated strategies exhausted?
**No.** The funnel shows healthy setup supply; the regime work shows a real risk-on
edge; the gap is cost/venue/downtime, not absence of alpha. **No new strategy is
warranted.** One verified production fix (re-cost + venue routing + S3 parity) is worth
more than any speculative alpha idea — exactly the brief's instruction.
