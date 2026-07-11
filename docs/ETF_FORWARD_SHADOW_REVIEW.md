# ETF FORWARD SHADOW REVIEW -- 2026-07-12

_Shadow window: 2026-07-12 -> 2026-07-12 (1 trading day(s)). Regime: calm
(VIX21ma ~18.0, contango ratio ~1.179). Gates: level gate open 1/1 days; ts gate open 1/1 days.
Research-side columns (rate/corr) come from etf_streams.csv (2021+) and are context,
not forward evidence. Pre-registered decision rule: KEEP if shadow rate >= 40% of
research rate at >=15 shadow days AND corr-to-QQQ < 0.5; REMOVE if < 40% at >=15 days
or corr >= 0.5 sustained; otherwise NEEDS MORE DATA._

| stream | fired | shadow days | research rate/day | expected fires | missed | overlap w/ QQQ-fire-days | research corr to S5_QQQ | recommendation |
|---|---|---|---|---|---|---|---|---|
| S1_GLD | 0 | 1 | 0.05 | 0.0 | 0 | 0% | -0.02 | NEEDS MORE DATA |
| S1_SMH | 0 | 1 | 0.09 | 0.1 | 0 | 0% | 0.19 | NEEDS MORE DATA |
| S1_XLK | 0 | 1 | 0.07 | 0.1 | 0 | 0% | 0.13 | NEEDS MORE DATA |
| S5_DIA | 0 | 1 | 0.13 | 0.1 | 0 | 0% | 0.17 | NEEDS MORE DATA |
| S5_QQQ | 1 | 1 | 0.19 | 0.2 | 0 |  |  | NEEDS MORE DATA |
| S5_SMH | 0 | 1 | 0.26 | 0.3 | 0 | 0% | 0.31 | NEEDS MORE DATA |
| S5_SPY | 1 | 1 | 0.15 | 0.2 | 0 | 100% | 0.31 | NEEDS MORE DATA |
| S5_XLE | 0 | 1 | 0.22 | 0.2 | 0 | 0% | 0.03 | NEEDS MORE DATA |
| S5_XLF | 0 | 1 | 0.16 | 0.2 | 0 | 0% | 0.14 | NEEDS MORE DATA |

## Day-1 observations (evidence, not verdicts)
- 2/9 streams fired (S5_QQQ, S5_SPY) on the same day -- one overlap datapoint;
  research-side corr S5_SPY~S5_QQQ is 0.31, so same-day firing with different
  instruments is expected occasionally, not yet evidence of duplication.
- Zero missed opportunities computable yet: expected fires per stream at 1 day are
  all < 0.3, so every zero is within expectation.
- Both gates open all day(s); no gate-blocked signals so far -- gate DECISIONS are
  logged but undifferentiated until a stress day arrives.

## Bottom line
All 9 streams: **NEEDS MORE DATA** (1 shadow day vs the 15-day pre-registered
minimum). No stream shows disqualifying behavior; the two that fired did so at
plausible rates. Re-run this review at >=15 shadow days (~2026-08-01); the decision
rule above is frozen now so the future verdict cannot be fitted to the data.
