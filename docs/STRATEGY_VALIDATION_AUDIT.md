# STRATEGY VALIDATION AUDIT -- 2026-07-12

_Not a parity audit (execution) -- a VALIDATION audit (provenance). For every
strategy: origin, validated timeframe/data/assumptions, whether live preserves
them, expected vs actual signal counts, and why they differ. Every number below
comes from an existing measurement (verify_liveness, parity auditor, S2/S3
funnels, shadow); nothing estimated._

| Q | S1 Asian Sweep | S2 Gold FVG | S3 Abnormal Vol | S4 Multi-Sweep | S5 ORB | OVN | BTC Sweep | BTCTREND / XSMOM |
|---|---|---|---|---|---|---|---|---|
| **1. Original paper** | none -- in-house (liquidity-sweep/ICT concept), validated internally | FVG concept (ICT); validated in-house (full_yearly) | in-house (volume-surge continuation) | in-house (S1 + EMA200 regime) | Zarattini/Aziz/Barbon ORB (SSRN 2023/24) | Boyarchenko-adjacent overnight literature, in-house calendar variant | in-house (S1 ported to crypto) | Moskowitz/Ooi/Pedersen 2012; Donchian |
| **2. Validated timeframe** | hourly | **DAILY** | daily | hourly | paper: 5-min; OUR validation: hourly approx (declared "coarse" in full_yearly) | daily | hourly (1h) | daily |
| **3. Validated data source** | Alpaca ETF ext-hours (QQQ) | GLD ETF daily | QQQ daily | Alpaca ETF (QQQ+SPY) | QQQ ETF hourly (+1-min in master lineage) | QQQ ETF daily | Binance BTCUSDT | ETF daily |
| **4. Key assumptions** | Asian-session bars exist (18-02 ET); volume for VWAP; 16:00 close for EMA | **overnight GAPS (daily bars)** | daily volume + green close | as S1 + 200d EMA | a 9:00 bar approximating the opening range; opening-auction structure | enter near close, exit at open | 24/7 continuous; UTC sessions | daily closes |
| **5. Live preserves them?** | **YES** (post-parity: 1200-bar fix restored EMA/HV; ext-hours bars verified present) | **YES since 2026-07-12** (was NO: hourly port made FVG unsatisfiable -- 0 fires/75d) | **PARTIAL**: live z-score variant is a strict SUBSET (97% overlap) of the validated rule but fires ~4/yr vs validated ~15/yr -- 73% of validated signals never trade | **YES** (post-parity) | **PARTIAL**: ETF side yes; on NAS100 CFD the 9:00 ET bar is NOT an opening range (23h continuous market, no auction) -- the "ORB" premise weakens on MT5 | **YES** (window entry ~close; catastrophe stop is additive) | **PARTIAL**: validated on Binance spot, trades Pepperstone CFD (basis/spread differ; 24/7 preserved) | **YES** (daily rules on daily data) |
| **6. Expected signals (historical)** | 332/7y bar-level pre-GEX (~47/yr) | ~16 trades/yr (daily lineage, replayed 07-12) | validated ~15/yr | 387/7y (~55/yr) | 3364/7y bar-level (~1.3/day); ~50 trades/yr engine-level | 2 entries/wk (calendar) | ~10-20/yr | sparse (monthly/regime) |
| **7. Live actually generates** | replay-verified firing (latest same-day); live trades gated by GEX -> ~11/yr design | 0 before fix (structural); expect ~16/yr from 07-14 | **~4/yr** (the subset) | replay-verified firing | 3 signals on first clean day (on-model); VPS fills pending | entries fired when scheduled (over-buy era fixed) | evaluations verified; sparse by design | rebalances on schedule |
| **8. Why they differ** | pre-fix: timezone + bar-starvation (FIXED); GEX gate is designed-in | wrong-timeframe port broke the gap assumption (FIXED to daily lineage) | **provenance drift: someone tightened the rule (z>1.5 + ret>1% vs 1.3x + green) without re-validation.** Not unsafe (subset), but 73% of the validated edge is unharvested. POST-WINDOW decision: revert to validated rule or re-validate the strict variant | as S1 | hourly-approx vs 5-min paper is a DECLARED validation choice, not drift; CFD opening-range weakness is unmeasured -- the fill ledger + month data will show if MT5-S5 underperforms ETF-S5 | none material | venue swap unquantified: compare MT5 BTC fills vs Binance-data expectations at month-end | none |

## Verdict summary

| strategy | validation integrity | action |
|---|---|---|
| S1, S4, OVN, BTCTREND/XSMOM | **YES** -- assumptions preserved | none |
| S2 | **YES since 07-12** (was NO -- caught & fixed via lineage port) | own clock restarted |
| S3 | **PARTIAL -- provenance drift found by this audit** | post-window: revert to the validated 1.3x rule or gauntlet the strict variant; until then expectation = 4/yr, not 15 |
| S5 | **PARTIAL on CFD only** -- ETF premise intact; CFD "opening range" premise structurally weaker | measure, don't guess: month-end MT5-vs-ETF S5 comparison from fills |
| BTC | **PARTIAL** -- venue swap (Binance-validated, CFD-traded) | month-end: fills vs expectation |

## The audit's meta-finding
Three of eight strategies carried silent validation drift (S2 timeframe, S3 rule
tightening, S5/BTC venue semantics). None was caught by parity checks -- parity
verifies the code matches ITSELF across environments; validation drift is the code
no longer matching ITS EVIDENCE. This audit class should re-run whenever a strategy
is ported across timeframe, venue, or data source.
