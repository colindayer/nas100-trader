# S3 Validation Review: Research vs Live Implementation

**Date**: 2026-07-12
**Status**: READ-ONLY (no production or strategy code modified)
**Script**: `scripts/s3_validation_review.py`

---

## Executive Summary

The live S3 implementation has **drifted substantially** from the validated research specification across **five independent dimensions**. When tested head-to-head on identical QQQ daily data (2019–2026):

- The live version fires **85% fewer signals** than the research version.
- The live version **goes negative out-of-sample** (2024–2026: −0.39%/yr) while the research version stays positive (+0.78%/yr).
- The headline `z > 1.5` tightening does **not** improve robustness — it removes profitable and unprofitable trades at roughly equal rates.
- Removing the validated RR=2.5 profit target further degrades performance.

### Recommendation: **REVERT**

Revert the live S3 to the validated research specification (ratio > 1.3, green candle, bull+GEX filters, RR=2.5 target, 20-day lookback). The live tightening is not a refinement — it is a different, unvalidated strategy that happens to share the S3 name.

---

## 1. Specification Differences

| Parameter | Research (`full_yearly.py`) | Live (`live_trader.py`) | Drift? |
|---|---|---|---|
| **Volume signal** | `Volume / ma20 > 1.3` (simple ratio, 20-day) | `(V − mean66) / std66 > 1.5` (z-score, 66-day) | **YES** |
| **Price signal** | `Close > Open` (green candle) | `(Close − Open) / Open > 0.01` (≥1% return) | **YES** |
| **Regime filter** | `SPY EMA50 > EMA200` (bull) + `GEX < 0` | `VIX < 25` (vix_mult > 0) | **YES** |
| **Profit target** | `RR = 2.5` (5% target, exits at target) | **NONE** (exit only on stop or 5-day hold) | **YES** |
| **Lookback** | 20-day MA | 66-day rolling stats | **YES** |
| **Universe** | QQQ only | QQQ, GLD, GDX, SLV, USO | **YES** |
| **Risk/trade** | 0.4% | 0.4% | Same |
| **Stop** | 2.0% | 2.0% | Same |
| **Max hold** | 5 days | 5 days | Same |

Five independent departures from the validated spec. Each was made without re-running the validation gauntlet.

---

## 2. Head-to-Head Results (QQQ daily, identical data)

### In-Sample (2019–2023, GEX available)

| Metric | Research | Live | Delta |
|---|---|---|---|
| Trades | 19 | 5 | −14 |
| Trades/year | 3.8 | 1.0 | −2.8 |
| CAGR | +0.37% | +0.45% | +0.08% |
| Sharpe | 0.53 | 0.85 | +0.32 |
| PF | 1.82 | 10.84 | +9.01 |
| MaxDD | −1.06% | −0.23% | +0.84% |
| Expectancy | $9.68 | $45.20 | +$35.52 |
| Win rate | 63.2% | 80.0% | +16.8% |
| Avg R | +0.272R | +1.153R | +0.881R |

**⚠️ Statistically meaningless.** Five trades over 5 years cannot support a Sharpe of 0.85 or a PF of 10.84. The live version looks better *per trade* but draws from a sample too small to evaluate.

### Out-of-Sample (2024–2026, no GEX)

| Metric | Research | Live | Delta |
|---|---|---|---|
| Trades | 21 | 6 | −15 |
| Trades/year | 8.8 | 2.5 | −6.2 |
| CAGR | **+0.78%** | **−0.39%** | **−1.17%** |
| Sharpe | 0.62 | −0.33 | −0.95 |
| PF | 1.57 | 0.57 | −1.00 |
| MaxDD | −1.91% | −2.13% | −0.22% |
| Expectancy | $+8.95 | $−15.47 | −$24.43 |
| Win rate | 57.1% | 50.0% | −7.1% |
| Avg R | +0.255R | −0.354R | −0.608R |

**The live version is negative out-of-sample.** The research version remains positive and consistent. The "tightening" did not improve robustness — it destroyed the edge.

### Full Period (2019–2026)

| Metric | Research | Live | Delta |
|---|---|---|---|
| Trades | 40 | 11 | −29 |
| Trades/year | 5.4 | 1.5 | −3.9 |
| CAGR | +0.50% | +0.18% | −0.32% |
| Sharpe | 0.55 | 0.24 | −0.31 |
| PF | 1.67 | 1.54 | −0.13 |
| MaxDD | −1.91% | −2.13% | −0.22% |

---

## 3. Yearly Performance

| Year | Research | Live |
|---|---|---|
| 2019 | −0.3% | — |
| 2020 | +2.0% | +0.9% |
| 2021 | −0.0% | +1.1% |
| 2022 | −0.4% | −0.2% |
| 2023 | +0.5% | +0.5% |
| 2024 | +0.9% | +0.2% |
| 2025 | +0.3% | **−1.2%** |
| 2026 YTD | +0.7% | — |

The live version skips entire years (2019, 2026 = zero trades) and goes negative in 2025.

---

## 4. Six OOS Splits

### Research (full 2019–2026)

| Split | Trades | Return | Sharpe |
|---|---|---|---|
| 1 | 9 | +1.93% | 1.42 |
| 2 | 5 | −0.23% | −0.29 |
| 3 | 2 | −0.39% | −1.14 |
| 4 | 2 | +0.33% | 7.50 |
| 5 | 10 | +0.71% | 0.59 |
| 6 | 12 | +1.40% | 0.91 |

**4/6 positive**, consistent positive aggregate. Small but real.

### Live (full 2019–2026)

| Split | Trades | Return | Sharpe |
|---|---|---|---|
| 1 | 1 | +0.87% | ~0 |
| 2 | 1 | +1.12% | ~0 |
| 3 | 1 | −0.23% | ~0 |
| 4 | 2 | +0.50% | 3.16 |
| 5 | 2 | +0.70% | 13.34 |
| 6 | 4 | **−1.65%** | −1.26 |

Mostly single-trade splits — no statistical weight. The last split (most recent data) is negative.

---

## 5. Does `z > 1.5` Improve Robustness? (Isolation Test)

To isolate the z-score effect, both variants used identical research filters (bull, GEX, RR=2.5) — only the volume measure changed:

| Metric | ratio > 1.3 | z > 1.5 | Delta |
|---|---|---|---|
| Trades (full) | 40 | 24 | −16 (−40%) |
| CAGR | +0.50% | +0.41% | −0.09% |
| Sharpe | 0.55 | 0.46 | −0.09 |
| PF | 1.67 | 1.70 | +0.03 |
| Expectancy | $9.38 | $12.72 | +$3.34 |

**Verdict: z > 1.5 improves per-trade quality marginally (PF +0.03, expectancy +$3.34) but CUTS 40% of trades and reduces overall CAGR and Sharpe.** The quality improvement does not compensate for the frequency loss. The z-score is not selecting better trades — it's just selecting *fewer* trades.

### Signal Overlap Analysis

| | Count |
|---|---|
| Research signals | 48 |
| Live signals | 12 |
| Overlap (both fire) | 7 |
| Research-only | 41 |
| Live-only | 5 |

The live filter removes **85.4%** of validated research signals. The removed signals include numerous +3% to +5% winners (e.g., 2019-03-08 +4.3%, 2021-05-19 +3.9%, 2023-03-15 +3.7%, 2025-11-21 +5.0%, 2026-03-31 +5.0%). It is not selectively filtering out losers.

---

## 6. Does the RR=2.5 Target Add Value? (Isolation Test)

Using the research signal, with vs without profit target:

| Metric | RR=2.5 target | No target | Delta |
|---|---|---|---|
| CAGR (IS) | +0.37% | +0.10% | **−0.26%** |
| Sharpe (IS) | 0.53 | 0.18 | **−0.35** |
| PF (IS) | 1.82 | 1.16 | **−0.66** |

The RR=2.5 profit target **significantly improves performance**. Removing it (as the live version does) cuts CAGR by ~70% and Sharpe by ~65%. This is consistent with the edge's fundamental structure: profits come from the occasional 2.5R+ winner. Without a target, winners are cut short at whatever the 5-day hold produces.

---

## 7. Root Cause Analysis

The live S3 is not a "tightened" version of the research S3. It is a **different strategy** that shares the name. The five drifts compound:

1. **z-score > 1.5** (kills 85% of signals — the primary throttle)
2. **dayret > 1%** (stricter than green candle — removes modest up-days)
3. **VIX gate replaces bull+GEX** (different regime filter entirely)
4. **No RR target** (cuts 65% of the edge's alpha)
5. **66-day lookback** (slower volume baseline = different regime sensitivity)

Each drift was made without re-running the gauntlet. None is validated. Together they produce a strategy that barely trades (1.5/yr) and loses money out-of-sample.

### The multi-symbol expansion (QQQ + GLD + GDX + SLV + USO)

The live version adds 4 unvalidated symbols to compensate for the tighter QQQ filter. This is a different, unvalidated edge (commodity/mining volume momentum ≠ QQQ equity volume momentum). No walk-forward, no OOS test, no correlation analysis was run on these symbols. The research explicitly validated QQQ-only.

---

## 8. Recommendation: **REVERT**

The live S3 should be reverted to the validated research specification:

| Parameter | Value |
|---|---|
| Universe | QQQ only |
| Volume signal | `Volume / ma20 > 1.3` |
| Price signal | `Close > Open` (green candle) |
| Regime | SPY EMA50 > EMA200 (bull) + GEX < 0 |
| Risk | 0.4% |
| Stop | 2.0% |
| Target | RR = 2.5 (5%) |
| Hold | 5 days max |
| Lookback | 20-day MA |

### Why not KEEP LIVE?
- Negative OOS (−0.39%/yr)
- 1.5 trades/year is statistically untestable
- 5 unvalidated departures from the spec
- No evidence the tightening helps

### Why not NEEDS NEW GAUNTLET?
- The research version already passed the gauntlet
- The live version already failed it (negative OOS)
- A "new gauntlet" would mean validating a different strategy — not repairing S3
- If the z-score approach is desired, it can be tested as a *candidate* through the standard gauntlet pipeline, not adopted first and tested later

### Honest assessment of the research S3

The research S3 is the weakest strategy in the system (+0.50%/yr, Sharpe 0.55). It was always marginal. The z-score and filter changes were presumably intended to improve it — but the result is worse: the tightened version doesn't improve robustness, it simply removes enough trades to make evaluation impossible. A strategy that fires 5 times in 5 years cannot be validated or deployed.

If S3 is to be improved, the path is: (1) revert to the validated spec, (2) run any candidate change through the full gauntlet (yearly, OOS, 6-split, walk-forward), (3) adopt only if it improves CAGR + Sharpe without degrading OOS. The current live version would fail at step 2.

---

## Appendix: Scripts & Reproducibility

- **Analysis script**: `scripts/s3_validation_review.py`
- **Data**: `qqq_hourly_7y.csv` (aggregated to daily), `gex_history.csv`, yfinance (SPY, VIX)
- **Periods**: IS 2019-2023, OOS 2024-2026, Full 2019-2026
- **Costs**: 3 bps/side (6 bps round-trip)
- **No production code modified**
