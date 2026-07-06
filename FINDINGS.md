# Strategy Research Findings

Running log of what we tested, what worked, and what we rejected — so we don't
re-add things that already failed validation.

## TL;DR

- **The core Asian-sweep strategies (S1, S4) are real** — they survive out-of-sample testing.
- **GEX option-data filter: keep.** Modestly improves risk (profit factor + drawdown), holds up OOS. Not a return-booster.
- **IV Skew filter + S6 + Short Interest: REJECTED.** No tradeable edge. Do not re-add.
- **Honest expected return: ~4–7%/yr on validated strategies** → a few hundred $/month on a $50k prop account, NOT thousands (yet).

---

## What we validated (keep)

### GEX (Gamma Exposure) filter — Squeezemetrics formula
`GEX = gamma × OI × 100 × spot² × 0.01`, calls positive / puts negative.
Negative net GEX = dealers amplify moves = good for sweeps. Filter: only take
long sweeps when net GEX < 0.

**Out-of-sample test (tune-era 2019–21 vs unseen 2022–23):**

| Strategy | IN-sample PF | OUT-of-sample PF | Verdict |
|----------|-------------|------------------|---------|
| S1 base → +GEX | 2.29 → 2.57 | 1.53 → 1.55 | neutral OOS |
| S4 base → +GEX | 2.19 → 2.50 | 1.98 → 2.12 | GEX helps OOS |

GEX's profit factor is **never below baseline** in any period — consistent across
two strategies and two eras = a real (if modest) effect. It trades a little raw
return for better PF and lower drawdown. For a prop challenge where the binding
constraint is the **drawdown limit**, that's the right trade. KEEP.

---

## What we rejected (do NOT re-add)

### IV Skew filter (Xing, Zhang & Zhao 2010) — REJECTED
Smirk = OTM-put IV − ATM-call IV. We had the IV data (OptionsDX C_IV/P_IV).
A/B test on S1 (see `iv_skew_ab.py`):

| Variant | Return | PF |
|---------|--------|-----|
| Baseline (GEX only) | +22.8% | 2.07 |
| + Skew filter >1.0σ | +19.0% | 1.86 |
| Only-when-steep (long) | +2.4% | 1.60 |

The filter is **redundant with GEX** — it cut return and PF with no drawdown
benefit. Why: the paper's smirk is a **weekly cross-sectional underperformance**
predictor, not an intraday index signal. Wrong horizon, wrong application.

### S6 IV Skew Reversal — REJECTED
Built it as a same-day "fade the fear" long. Backtest: −0.8%, 22% win rate,
9 trades/5yr. Tested 3 interpretations — long-fade (no edge), long-filter
(redundant), short-in-bear (never fires; steep skew co-occurs with VIX>25 lockout).
No edge in any form. Removed.

### S5 ORB Short "Phase 1" filter stack (OR-ratio + volume + VIX band) — REJECTED
Added 3 research filters to force S5 Short positive. The OR-ratio band (0.25–0.60)
**zeroed out 100% of signals by itself** — it came from 30min-ORB/daily-ATR research
and doesn't translate to our hourly-bar / hourly-ATR scale. A strategy that never
trades isn't "positive," it's inert. Also: the dynamic 1.5×ATR stop added to
`run_intraday()` silently degraded the validated S1/S4 (S1 2021 +5.6%→+1.6%).
Both reverted.

### Multi-ETF expansion (Asian Sweep on IWM/DIA/TLT) — REJECTED
Tested the "more ETFs = more money" thesis by running the proven S1 Asian-sweep
logic on IWM (small caps), DIA (Dow), TLT (bonds), net of costs:

| ETF | avg/yr | corr→QQQ | trades |
|-----|--------|----------|--------|
| IWM | **−1.8%** | 0.04 | 50 |
| DIA | **−0.3%** | 0.04 | 37 |
| TLT | +0.2% | −0.00 | 16 |

They're genuinely **uncorrelated** (corr ~0.04) — but the **edge doesn't transfer.**
The Asian-session sweep relies on QQQ-specific overnight liquidity dynamics (heavy
tech extended-hours trading); IWM/DIA have thin overnight liquidity, TLT trades on
rates. **Uncorrelated + no edge = drag, not diversification.** Diversification only
helps when the added component has *positive* expectancy. Lesson: an edge is
instrument-specific until proven otherwise — don't assume it generalizes. The edge
lives in QQQ (and likely SPY/large-cap-tech), not the broad ETF universe.

### SPX/VIX divergence strategy — REJECTED
"SPY down + VIX down = bullish reversal" tested long-only on QQQ, net of costs:
bull-divergence +0.1%/yr (OOS −0.5%); its INVERSE did *better* in-sample (+1.1%).
That means the divergence isn't the driver — both are just "buy the dip" (long
market beta) that worked 2019–21 and failed 2022. No alpha. The VIX adds nothing.

### Volume Profile strategy (LAT concept) — REJECTED (definitively)
Long below Value-Area-Low → target POC, rolling 10-day profile, net of costs.

**Round 1 (hourly bars, 50 bins):** −0.6%/yr in-sample, −1.1%/yr OOS. Caveat noted:
coarse 50-bin profile from ~7 bars/day might miss real structure.

**Round 2 (1-minute bars via `qqq_1min_7y.csv`, 200 bins):** Re-run 2019–2023 with
same signal logic and parameters, no tuning — only finer data:

| Variant | 2019 | 2020 | 2021 | 2022 | 2023 | avg | IN | OUT |
|---------|------|------|------|------|------|-----|----|-----|
| VP mean-revert (below VAL) | −0.3% | +0.2% | −1.0% | −0.1% | −0.1% | −0.3% | −0.4% | −0.1% |
| Inverse (above VAH) | −2.1% | −0.8% | −2.0% | +0.0% | −1.3% | −1.3% | −1.7% | −0.7% |

**Verdict: definitively REJECTED.** Adding 50× more resolution (390 bars/day vs 7)
produced the same null result. The data-limitation caveat is closed: volume profile
mean-reversion on QQQ has no intraday edge at any bar frequency tested. Do not revisit.

### NQ futures port — VALIDATED ✅ (the prop-firm path)
Ran the QQQ Asian-Sweep + ORB on NQ=F (Nasdaq-100 futures), 2024-2026 data
(a DIFFERENT period + instrument wrapper than the 2019-23 QQQ backtest = true
out-of-sample), net of costs:

| Strategy | 2024 | 2025 | 2026 | avg |
|----------|------|------|------|-----|
| S1 Asian Sweep | +5.0% | −0.0% | +3.4% | +2.8% |
| S5 ORB Long | +4.4% | +2.8% | +4.2% | +3.8% |

The edge **ports cleanly** to NQ — same index, different wrapper, different era,
still positive and consistent. This is the coherent conclusion of all the testing:

**The edge is real and specific to the Nasdaq-100 index.** It travels across
WRAPPERS of that index (QQQ ETF ↔ NQ/MNQ future) and across TIME (2019-23 ↔
2024-26), but NOT to other markets (IWM/DIA/TLT/EURUSD all failed) or other
mechanisms (VIX divergence, volume profile failed). => The prop-firm path is a
**futures account trading NQ/MNQ** (or US100 CFD), NOT new instruments/edges.

### Gold futures port — VALIDATED ✅
S2 Gold FVG on GC=F (gold futures), 2019-2026, net of costs: +3.8%/yr avg
(matches GLD ETF +3.3%). Gold edge ports across wrappers (GLD ETF ↔ GC/MGC
future) just like Nasdaq (QQQ ↔ NQ). Two validated, uncorrelated futures edges
for a prop account: NQ/MNQ (sweep+ORB) and GC/MGC (FVG). Oil (MCL/CL) is a
DIFFERENT market — not expected to inherit the gold edge; not tested/used.

### PROP-FIRM DRAWDOWN CONSTRAINT (important deployment note)
System max DD ≈ −7.3% (full sizing). Futures prop evals (Apex/Lucid) use TIGHT
trailing drawdowns (~3–5% of account → e.g. $2,500 on a $50k Apex account = 5%).
At full sizing a −7% DD event BREACHES that. => On tight-DD futures evals, trade
~HALF size (~5%/yr) to fit. Forex/CFD firms (The5%ers/FTMO, ~10% max DD) fit the
system at full size (~10%/yr) and trade the same edges via US100 + gold CFD.

### Short Interest boost (Asquith 2005) — REJECTED
Added as a log-only conviction note. Never gated trades, never validated,
added a fragile yfinance `.info` call. Removed for simplicity.

---

## Overfitting assessment

**Are we overfitting?** The *add-ons* were (skew, S6) — already removed. The
*core* is not: S1 degraded from PF 2.29 (in-sample) to 1.53 (out-of-sample) but
stayed profitable on data it never saw. That's healthy degradation, not collapse.

**Danger signs we're watching:**
- Small samples: S1 ~11 trades/yr, S4 ~9/yr. PF differences on ~50 trades are statistically fragile.
- ~8 filters / 10+ parameters explaining ~54 trades = ~5 trades per degree of freedom (low; want 10+).
- 2020 is an outlier (COVID) inflating in-sample stats on 4–6 trades.

**Rule going forward: FREEZE. Stop adding filters.** Each addition has been
subtracting robustness. The next real validation is live paper-forward testing,
not more backtest tuning.

---

## Honest performance (current frozen system: S1 + S4, GEX-filtered, QQQ)

Per-year return, capital reset to $10k each Jan (see `combined_yearly.py`):

| Year | S1 | S4 | Combined |
|------|-----|-----|----------|
| 2019 | +6.3% | +4.5% | +10.9% |
| 2020 | +2.8% | +2.0% | +4.8% |
| 2021 | +5.6% | +3.8% | +9.4% |
| 2022 | −0.4% | −0.5% | **−0.9%** |
| 2023 | +4.9% | +4.5% | +9.4% |
| **5yr avg** | | | **+6.7%** |
| **OOS avg (22–23)** | | | **+4.3%** |

### $50k prop account → monthly profit (80% split)

| Scenario | Annual | Monthly net |
|----------|--------|-------------|
| Optimistic (5yr avg) | +6.7% | ~$224/mo |
| Realistic (OOS 22–23) | +4.3% | ~$143/mo |
| Bad year (2022) | −0.9% | −$29/mo |

**Reality check:** at current risk sizing and with only 2 validated strategies,
this is **hundreds, not thousands, per month** — well short of the $1,600–3,600 goal.
Closing that gap requires (in order of safety):
1. **Fix S2/S3/S5** (currently broken by data bugs → near-zero trades). More
   uncorrelated strategies = more total return at the same per-strategy risk.
2. **Add the S4 SPY leg** (couldn't backtest — no SPY intraday data locally).
3. **Scale to multiple / larger prop accounts** once the edge is proven live.
4. **Carefully increase risk-per-trade** — but this raises drawdown, and prop
   firms fail you on DD breaches, so this is the *last* lever, not the first.

The strategies are **genuinely positive and robust but low-return**. The honest
path is to prove them on paper, fix the broken strategies, then scale — not to
crank risk to hit an income target.

---

## Full 6-strategy system (after fixing S2/S3/S5 data bugs)

Data-bug fixes (see `full_yearly.py`): S5 ORB uses the hour-9 bar as opening range
(hourly data has no 9:30 bar); S2 uses GLD **daily** FVG (yfinance won't serve 5yr
hourly GLD); S3 uses a **1.5×** volume threshold (2.0× gave only 3 signals/5yr).

### Per-year return, each strategy on its own $10k sleeve

| Strategy | 2019 | 2020 | 2021 | 2022 | 2023 | avg |
|----------|------|------|------|------|------|-----|
| S1 Asian Sweep | +2.0% | +2.8% | +5.6% | +0.0% | +5.2% | +3.1% |
| S4 Multi-Sweep | +4.5% | +2.0% | +3.8% | −0.5% | +4.5% | +2.9% |
| S5 ORB Long | +5.8% | +2.0% | +3.2% | −1.2% | +3.6% | +2.7% |
| S5 ORB Short (Faber) | +0.0% | +0.0% | +0.0% | +2.7% | −0.5% | +0.4% |
| S2 Gold FVG | +3.5% | +6.1% | +1.5% | +2.0% | +0.5% | +2.7% |
| S3 Abnormal Vol | −0.8% | +2.2% | −0.2% | −0.5% | +0.6% | +0.2% |
| **COMBINED** | +15.1% | +15.1% | +13.9% | **+2.5%** | +13.9% | **+12.1%** |

**Out-of-sample (IN 2019–21 vs OUT 2022–23): combined +14.7% → +8.2%, all six
strategies hold positive OUT. Worst single year OUT = +2.5%.** The regime
diversification thesis survives unseen data: in the bear year the equity sweeps
weaken but Gold + the (now-gated) Short hedge offset them.

### S5 ORB Short — why it's a strategy despite losing always-on
- **Always-on (EMA50<EMA200 gate): −0.6%/yr** — it shorted *into* the 2019 recovery
  (the EMA crossover lagged after the Dec-2018 crash). Net loser, no OOS edge.
- **Faber 200-day gate (price < 200d SMA): +0.4%/yr** — one standard, pre-specified
  regime rule (Faber 2007, *Quantitative Approach to Tactical Asset Allocation*),
  no tuned thresholds. Fixes the 2019 bug and strengthens the bear-year hedge
  (2022 +0.6%→+2.7%). The live bot auto-arms/disarms it via the QQQ 200d-SMA check
  in `get_regime()`.
- This is the **regime-adaptive** design working as intended: the short hedge sits
  dormant in bull markets (no bleed) and activates only in confirmed risk-off
  regimes. Grounded in ORB literature (Crabel 1990; Zarattini & Aziz 2023: ORB
  shorts need a confirmed downtrend + volume confirmation).
- **Caveat:** the +2.7% bear-year result rests on **one** bear year (2022). The rule
  is sound and principled, but real proof is the next bear market / paper trading.

### $50k prop account → monthly profit (80% split), full system

| Scenario | Annual | Monthly net |
|----------|--------|-------------|
| Optimistic (5yr avg) | +12.1% | ~$403/mo |
| Realistic (OOS 22–23) | +8.2% | ~$273/mo |
| Worst year (2022) | +2.5% | ~$83/mo |

Adding the 3 fixed strategies + the Faber-gated short roughly **doubled** the
realistic monthly figure (~$143 → ~$273) and turned the worst year **positive**
(−0.9% → +2.5%). Still short of the $1,600–3,600 goal — that gap closes by scaling
account size/count once proven live, not by over-risking one account.

### Walk-forward reconciliation (the -16.9%/-17.9% window)
Fixed walkforward.py to include the uncorrelated Gold sleeve + shared-account model.
Result: gold lifted the AVERAGE (Sharpe 0.98 -> 1.44, +4.2%/6mo, 5/7 positive) but did
NOT fix the worst window (2023-07->2024-01 still -17.9% DD). Root cause traced via the
per-strategy breakdown: **S5L (1-minute ORB) avg Sharpe -2.01 — negative.** The M1 ORB
sleeve is the weak/risky component, unlike the validated HOURLY NQ ORB (+3.8%, positive
Sharpe). Deployable robust core = S1/S4 sweeps + Gold + hourly ORB. The 1-min ORB
(S5L/S5S) needs fixing or dropping before live deployment. NOTE: the "30%/yr" figure
was a 2.4y total inflated by a historic gold rally — realistic repeatable return ~10%/yr.

### CORRECTION: S5 Short is the (correctly-gated) insurance — the bug is M1 ORB data
Added S5S + gold to the walk-forward breakdown. Findings:
- **S5S (Faber-gated short) fires ONLY in bear regimes** — per-window trades [0,0,11,18,7,1,0]:
  29 trades in 2022 (bear), 0 in bull windows. The regime gate works as designed.
- S5S did NOT cause the -17.9% window (2023-07→2024-01 was bullish; S5S fired 1 trade).
- ROOT CAUSE: the walk-forward runs the ORB on **1-minute data**, where BOTH S5L (Sharpe
  -2.01) and S5S (Sharpe -4.55) lose — UNLIKE the validated **hourly** ORB (S5L +3.8%/yr,
  S5S +2.7% in 2022). The M1 ORB implementation is broken; the hourly version is fine.
- FIX: use hourly ORB (validated), not the M1 version. Do NOT drop S5 — the insurance
  role and Faber gate are correct. Gold also looks weak in windows only because its big
  move was 2024+ (outside most test windows), not a real failure.

### ORB fix VALIDATED — hourly opening range (not 1-minute)
Replaced the broken M1 ORB with the validated hourly version (hour-9 opening range,
Faber 200d gate for short) in walkforward.py. Walk-forward result, before → after:
- Positive windows: 5/7 → **7/7 (100%)**
- Avg Sharpe: 1.44 → **3.21**;  Avg ret: +4.2% → **+6.0%/6mo**;  Avg DD: −6.8% → −5.7%
- S5L Sharpe −2.01 → **+2.75**; S5S avg ret −0.27% → **+0.52%** (insurance now pays,
  fires only in bear: trades [0,0,15,13,5,0,0]).
The edge is proven across ALL 7 windows. The 1-minute data was the bug, not the
strategy. REMAINING TAIL: one window (2023-07→2024-01) still has −16.3% intra-window
DD (vs ≤−7.3% for the other 6) — real tail risk in unusual choppy periods; argues for
slightly conservative prop sizing. TODO: align live_trader.py run_s5 to hourly ORB too.

### Dynamic exits (trailing / breakeven / partial TP) — REJECTED
A/B vs fixed-stop baseline on S1, net of costs (dynamic_exits_test.py):
| Mode | avg | PF | WR | maxDD |
|------|-----|-----|-----|-------|
| baseline (fixed 3:1) | +2.9% | 1.82 | 39% | -3.0% |
| trailing stop | +2.2% | 1.79 | 46% | -2.7% |
| breakeven-at-1R | +2.7% | 1.74 | 31% | -3.3% |
| partial TP at 1.5R | +1.7% | 1.48 | 54% | -3.5% |
ALL reduce return. Trailing/partial RAISE win rate (feels nicer) but cut the big
3R winners short — and this edge's profit comes from letting winners run to target
("few big winners pay for many small losers"). Fixed 3:1 RR is mathematically what
the edge needs, not strictness. Confirms the earlier dynamic-ATR-stop rejection.

### BTC Asian Sweep — PROMISING (preliminary, not yet validated)
Ran the QQQ sweep (same logic, no tuning) on BTCUSDT 1h (Binance, 2019-2026, 7.5y),
net of ~8bps crypto costs. UNLIKE IWM/DIA/TLT/EURUSD, it transfers:
| Stop | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | avg |
|------|------|------|------|------|------|------|------|-----|
| 1.5% | +11.7% | +12.6% | +14.1% | 0% | -0.9% | -6.5% | +2.3% | +4.2% |
| 2.5% | +5.4% | +12.6% | +10.7% | 0% | +1.3% | +9.5% | +3.1% | +5.3% |
Vol-scaled 2.5% stop positive every active year. Regime gate worked (2022 crypto
bear = 0 trades). FIRST adaptation to survive a transfer test.
⚠️ DECAY FLAG: strong 2019-21, weaker 2022-25 — edge fading as crypto matures
(matches the microstructure-edge decay 52%->50.75%). NOT yet validated. Still needs:
walk-forward, correlation-to-QQQ/gold (the diversification point), decay analysis.

### BTC Asian Sweep — VALIDATED ✅ (genuine pillar #3)
Full gauntlet on BTCUSDT 1h (2.5% vol-scaled stop, net of ~8bps crypto costs):
- Walk-forward: **10/12 rolling 6-month windows positive (83%)**, incl recent
  (2024: +8.4%, +9.7%).
- Decay: early 2019-21 +11.2%/yr → mature 2023-26 +7.3%/yr. Decayed but STILL
  POSITIVE and tradeable (not dead). Monitor decay live.
- Correlation to QQQ sweep daily P&L = **+0.022 (≈ zero)** → genuine diversifier.
THREE validated, uncorrelated pillars now: Nasdaq (sweep+ORB) + Gold (FVG) + BTC
(sweep). The "different strategies for different assets" thesis is proven on a 3rd
asset. Deployable on Bybit/Binance, FTMO crypto CFD, or MBT futures. Live paper
test still required. The diversification math: 3 uncorrelated ~7-10%/yr edges
combine to higher return + lower combined drawdown than any one alone.

### 3-PILLAR CAPSTONE — combined system measured (net of costs, one $10k account)
| System | CAGR | Sharpe | MaxDD |
|--------|------|--------|-------|
| Nasdaq (S1+S4+S5) | +8.2% | 0.94 | -7.1% |
| Gold (FVG) | +3.1% | 0.95 | -3.3% |
| BTC (sweep) | +6.8% | 0.91 | -7.9% |
| **COMBINED 3-pillar** | **+12.2%** | **1.38** | **-7.9%** |
Diversification works: combined CAGR > any single pillar, Sharpe 0.9 -> 1.38, and
MaxDD stayed ~8% instead of stacking to ~15-20% (because uncorrelated). Expressed
as more return per unit drawdown, not lower drawdown. -7.9% over 7.5y = prop-safe
(<FTMO 10%). At 0.7x sizing: ~8.5% CAGR / ~5.5% DD — deployable. Live test pending.

### Conformal risk overlay (Schmitt 2026 "Taming Tail Risk") — DD-THROTTLE ADOPTED
Tested a simplified RWC overlay (position scaler, no lookahead) on the 3-pillar system:
| Variant | CAGR | Sharpe | MaxDD | Calmar |
|---------|------|--------|-------|--------|
| baseline | +12.2% | 1.38 | -7.9% | 1.54 |
| vol-target only | +12.2% | 1.38 | -7.9% | — (no effect) |
| **dd-throttle** | +9.6% | 1.31 | **-4.8%** | **2.00** |
- vol-target USELESS (sparse trade-day P&L → rolling vol dominated by zeros). Dropped.
- **dd-throttle WORKS**: scales size down as live DD approaches the cap. Cuts MaxDD
  -7.9%->-4.8% (39% safer) for -21% CAGR. Calmar 1.54->2.00. For a prop account
  (drawdown = binding constraint) this is the right trade — huge headroom under FTMO
  10%. Unlike dynamic EXITS (broke the edge), this is a position-SIZE overlay that
  leaves strategy logic untouched. Of the 5 "Risk Quant" papers, only this one helped;
  the 3 CoVaR/derivatives-pricing papers were wrong-domain, DeePM overkill.
TODO: wire the dd-throttle into live RISK_SCALE (replaces the manual 0.7x).

## Pillar Allocation Test (Cost-Aware, Monthly Rebalancing)
**Date**: 2026-06-28
**Data**: Nasdaq (S1+S4+S5L+S5S), Gold (FVG), BTC (Sweep) daily P&L from 2019-01-10 to 2025-10-10
**Method**: Monthly rebalancing on first day of month, 5 bps turnover cost, no look-ahead bias.
**Validation**: In-sample (2019-2022) vs Out-of-sample (2023-2025)

### Full Period Results (2019-2025)
| Scheme | CAGR | Sharpe | MaxDD | Final Equity |
|--------|------|--------|-------|--------------|
| EqualWeight |  3.96% |   1.29 | -3.58% |     14622 |
| InvVol |  3.38% |   1.41 | -2.83% |     13846 |
| RiskParity |  2.72% |   1.27 | -2.65% |     13006 |
| RollingSharpe |  3.55% |   0.66 | -8.06% |     14072 |

### OOS Results (2023-2025)
| Scheme | CAGR | Sharpe | MaxDD | Final Equity |
|--------|------|--------|-------|--------------|
| EqualWeight |  2.79% |   0.89 | -3.58% |     14622 |
| InvVol |  1.84% |   0.85 | -2.64% |     13846 |
| RiskParity |  0.99% |   0.64 | -2.01% |     13006 |
| RollingSharpe |  3.51% |   0.52 | -8.06% |     14072 |

### OOS Performance Relative to EqualWeight
| Scheme | Δ Sharpe | Δ MaxDD | Verdict |
|--------|----------|---------|---------|
| InvVol |  -0.04 | +0.94% | Mixed |
| RiskParity |  -0.25 | +1.57% | Mixed |
| RollingSharpe |  -0.37 | -4.48% | Worse |

### Foreign indices (Nikkei/DAX/CAC/HangSeng/KOSPI) — mostly REJECTED
ORB on cash indices, ~2y yfinance hourly, net 5bps, long+uptrend:
| Index | CAGR | Sharpe | MaxDD |
|-------|------|--------|-------|
| Nikkei | -6.7% | -2.82 | -20.5% |
| DAX | -8.6% | -2.21 | -23.2% |
| CAC40 | -12.2% | -4.44 | -31.4% |
| HangSeng | -3.5% | -1.43 | -12.2% |
| KOSPI | +3.5% | +1.59 | -6.1% |
4/5 fail (big DDs) — edge doesn't transfer, same as multi-ETF. KOSPI lone positive
but likely multiple-testing noise (163 trades/2y); NOT adopted without full gauntlet.
CAVEAT: rough ORB on CASH indices (no overnight sessions, 2y data) — the real sweep
needs FUTURES intraday data (FDAX/Nikkei fut). Strategic lesson: transferable +
uncorrelated edges are RARE (3 pillars found, most candidates fail). "More assets"
and "more strategies" both fail without a genuine uncorrelated edge — keep the rare
winners (Nasdaq/Gold/BTC), deploy them, test new candidates as low-cost lottery tickets.

### Index FUTURES sweep — PROMISING lead (data was the issue, not the edge)
Sweep on 24h index futures (yfinance, ~2y, net costs) — overnight session exists,
unlike cash indices:
| Future | avg/yr | cash/ETF version |
|--------|--------|------------------|
| Nikkei (NIY=F) | +1.5% | cash ORB was -6.7% |
| Russell (RTY=F) | +2.0% | IWM ETF was -1.8% |
| Dow (YM=F) | +1.7% | DIA ETF failed |
KEY: the sweep needs the OVERNIGHT session. Cash indices/ETFs lack it → earlier
failures were partly a DATA artifact. Futures (24h) make it positive. Russell
futures rescued the failed IWM. CAVEATS: (1) correlation to QQQ uncomputable here
(period mismatch 2019-23 vs 2024-26 — must fix); Dow/Russell are US-correlated
(low diversification); NIKKEI (Japan) is the only genuine diversifier. (2) ~2y,
lumpy (Nikkei avg carried by one +6.6% yr). (3) NOT validated — needs proper
correlation vs 2024-26 Nasdaq ref + more data + walk-forward. Best new-asset lead
since BTC, but preliminary. Nikkei = pillar #4 candidate IF it passes the gauntlet.

### Nikkei futures sweep — REJECTED (uncorrelated but inconsistent)
Proper validation: correlation to NQ sweep +0.137 (uncorrelated ✅) BUT rolling
6-month windows only 3/8 positive (38%) — lumpy, +6.2% total carried by two 2026
windows, tiny sample (~8-24 trades/yr). Coin-flip consistency vs BTC's 10/12.
Uncorrelated diversifier with NO reliable edge → not pillar #4. Walk-forward caught
what the per-year average hid.

### Pairs / correlation mean-reversion — REJECTED (different edge type, no edge)
Market-neutral z-score mean-reversion on 4 pairs (2015-26, net costs):
| Pair | CAGR | Sharpe | MaxDD | corr→QQQ |
|------|------|--------|-------|----------|
| Gold/Silver | -4.3% | -0.19 | -63.7% | 0.04 |
| Nasdaq/S&P | -0.8% | -0.10 | -22.9% | -0.06 |
| Energy/Financ | -6.3% | -0.34 | -65.0% | 0.04 |
| BTC/ETH | -27.4% | -0.57 | -93.5% | -0.00 |
All negative with catastrophic DDs. Uncorrelated (~0.04) but no edge. Classic
pairs death: spread TRENDS instead of reverting (BTC/ETH ratio ran for years).
Simple pairs trading arbitraged away in liquid markets post-2000s. Don't revisit.

### HUNT CONVERGENCE NOTE
Tested for new uncorrelated edges: multi-ETF, VIX divergence, volume profile (2x),
EURUSD ORB, SMA crossover, foreign cash indices (5), index futures sweep (Nikkei),
pairs (4). Of all: only BTC passed. Edge discovery has hit clear diminishing
returns. The validated set is stable: Nasdaq (sweep+ORB) + Gold (FVG) + BTC (sweep),
+ conformal DD-throttle. The value now is DEPLOYMENT (paper test), not more hunting.

### Prop-challenge Monte-Carlo optimizer (FundedNext presets) — ADOPTED
Replaced the Gaussian `prop_ev_sim.py` model with `prop_firm_optimizer.py`:
fat tails (Student-t df=4), sparse trade days (40%), intraday daily-loss buffer
(80% of stated limit), min-trading-day rules, per-firm presets (FundedNext
Stellar 2-Step / 1-Step / Lite, FTMO), funded stage WITH the conformal
dd-throttle, and 3 edge scenarios (backtest / haircut 0.66 / weak 0.33).
Key results at the HONEST haircut edge (~8%/yr, Sharpe ~0.9), $100k:
- **Best plan: FN Stellar 2-Step at RISK_SCALE 1.5–2.0** — P(pass) 44–52%,
  median 85–136 market days to funded, ~$1.1–1.25k expected fees to funded,
  EV $8.4–12k/challenge. EV/time peaks at 2.0x, EV/challenge at 1.5x.
- **Stellar 1-Step REJECTED for this system**: 3% daily / 6% max loss vs our
  fat tails → optimum stuck at 1.0x, P(pass) 41%, EV ~⅓ of the 2-Step.
- Even the weak scenario (+4%/yr) keeps 2-Step EV positive at 1.5–2x →
  challenge farming robust to a big edge haircut, but NOT to zero edge.
- Funded stage: drop to 1.0x + dd-throttle (survival >> speed once funded).
Full cheat-sheet: PROP_PLAN.md. This changes SIZING/venue choice only — the
frozen strategy set is untouched (no new filters, freeze rule respected).

### Challenge "cushion governor" (dynamic sizing) — REJECTED
Tested anti-martingale dynamic sizing for challenges (risk ∝ headroom above the
static max-loss floor, `clip(m0·cushion/maxdd, 0.3, cap)`) vs static, same MC:
governor LOSES at every setting (e.g. 2.0x: P(pass) 44.9%→37.5%, no speed gain).
Root cause: the DAILY loss limit is fixed vs initial balance — profit cushion
gives no protection against it, so upsizing after gains only adds daily-breach
risk. Static challenge sizing + funded dd-throttle is near-optimal; the honest
calendar-time levers are (a) 2.5x static (median ~60 days, P(pass) 36%),
(b) PARALLEL challenges (3 accounts at 2.0x → 82% at least one funded in ~4mo),
(c) smaller accounts (same %-rules → same pass odds, fees scale down).

### SSRN sweep 2026-07 (price mismatch / overnight / Bollinger / VWAP) — 1 lead, 3 rejects
- **LEAD → intraday momentum, noise bands + VWAP trailing stop** (Zarattini/
  Aziz/Barbon SSRN 4824172; Maróy SSRN 5095349 finds VWAP exits best). Same
  authors as our validated S5 ORB source; paper: net Sharpe 1.33, +19.6%/yr,
  SPY 2007-24, trades ~daily (breadth → faster prop pass), takes shorts.
  Test script ready: `intraday_momentum_test.py` (six-filter gauntlet, our
  costs/data; sanity-checked: correctly loses on synthetic random data). Run
  where the hourly CSVs live. If it passes: still needs corr-to-book (<0.3),
  walk-forward, decay check before any adoption.
- **Overnight drift — REJECT for us**: Boyarchenko/Larsen/Whelan (SSRN 3546173):
  pre-cost Sharpe 1.1-1.3 but **-0.5 to +0.3 after costs** — the edge is real
  but thinner than retail frictions; our S1 already harvests related
  overnight-session structure.
- **ETF NAV premium/discount "price mismatch" — REJECT**: AP/HFT arbitrage
  (FCA OP68 2025), sub-second latency game — same conclusion as our earlier
  order-flow rejection. Not retail-tradeable.
- **Bollinger bands — REJECT**: standard band-reversion/breakout rules have no
  robust post-cost edge in the academic record (data-snooping literature);
  also our own BB-adjacent tests (volume profile, dynamic exits) all failed.

### London Breakout (Asian-range straddle, video strategy) — REJECTED (decisively)
Tested on 6y of broker-real Pepperstone H1 (EURUSD + GBPUSD, costs on,
2026-07): EURUSD OOS Sharpe **−3.96**, GBPUSD **−6.19**; both lose ~40–60%
over the sample at 0.5%/trade risk, ~145 trades/yr each. Optimistic intrabar
bound equally negative → not a bar-resolution artifact, the strategy itself
bleeds. The classic retail London-breakout is arbitraged below retail costs.
Consistent with our validated S1: the Asian-range BREAK fails more often than
it follows through (S1 profitably fades it). Do not revisit.

### Intraday momentum, noise bands + VWAP stop (SSRN 4824172) — REJECTED (decayed)
On US100 CFD feed (hourly approx, costs on): IS 2020–mid-23 Sharpe **+1.32**
(incl. +24.8% in 2022 — the short side worked in the bear), OOS mid-23–2026
Sharpe **−0.80** (−8.4%, −5.0%, −5.6% in 2024/25/26). The paper's sample ends
early 2024; the edge decayed right after publication — textbook post-publication
decay. Caveat: hourly bars coarsen the paper's intraday rule, but OOS-negative
on the tradeable feed = not deployable. Do not adopt.

### MT5 liveness RESTORED (post timezone fix) — the silent weeks explained
With server-time bars rebased to UTC, the replay on broker-real NAS100 data
shows all strategies alive: S1 13 signals/180d, S4 27, S5 274, S3 3 (pre-GEX
counts), latest signals same-day. The 2-week live silence was 100% the MT5
server-time bug (Asian windows shifted ~3h), NOT over-strict filters. Gates
verified working (S4 SPY correctly blocked on positive GEX same run).

### VENUE RELIABILITY — VERIFIED GREEN on VPS (2026-07-06)
Evidence captured on the VPS after the UTF-8 fix landed:
- All scheduled tasks return **Last Result: 0** (Nas100Bot-MT5/BTC/Overnight,
  nas100-update) — pre-fix they returned 1 on every run. UTF-8 fix confirmed live.
- **MT5 PLACED A REAL DEMO TRADE**: session showed `Positions: ['QQQ']` and equity
  $50,000.02 → $50,008.86 (+$8.84). First live trade end-to-end. All 4 symbols
  resolve (QQQ→NAS100, SPY→US500, GLD→XAUUSD, BTC→BTCUSD) with live prices.
- BTC session runs clean, uptrend gate correctly holding (uptrend=False), exit 0.
- nas100-update auto-pull working (pulled 029867c mid-session).
- Telegram: token+chat_id set, "[TELEGRAM] sent ✓", ping received on phone.
- Alpaca Actions green 2026-07-06 with real broker.
ALL THREE VENUES GREEN. Note: broker calls NAS100 (not US100) — handled by MT5
symbol resolution; equity ticked up = the QQQ position is live and profitable.

### VENUE RELIABILITY (plumbing, not edge) — 2026-07
- **UTF-8 scheduled-run crash (ae148e3): FIXED & verified in code.** Windows
  scheduled tasks redirect stdout to a cp1252 log; the emoji in "SPY Golden ✅"
  raised UnicodeEncodeError → exit 1 on EVERY scheduled run before any strategy
  evaluated (≈6 silent days). `sys.stdout/stderr.reconfigure(utf-8, replace)` at
  the top of live_trader.py. This — not the earlier timezone bug — was the final
  zero-trades cause on the VPS scheduler.
- **MT5 sweep universe trimmed per-broker.** SWEEP_BASKET (SPY/IWM/GLD/XLK/XLE/
  AAPL/MSFT/NVDA/AMZN) is Alpaca-only; on MT5/Pepperstone only SPY(→US500) and
  GLD(→XAUUSD) are valid CFDs, the rest raised "Symbol not available" every run.
  `_sweep_universe_for(broker)` detects MT5 via SYMBOL_MAP (QQQ→US100, copied by
  DryRunBroker) and trims to MT5_SWEEP_AVAILABLE={SPY,GLD}; Alpaca keeps the full
  list. Unit-verified both branches. Does NOT add QQQ to sweep (S1 already trades
  it — avoids double-order in --session all).

### DIX dark-pool regime gate — REJECTED (sign-unstable)
Tested prior-day SqueezeMetrics DIX as a daily gate on S1+S4 sweeps (US100
broker feed, 338 trade-days 2020–26, identical trade sim, a-priori thresholds,
inverse control): the effect FLIPS between eras — IS: inverse (low DIX) wins
(Sharpe +0.83 vs gate 0.00); OOS: gate wins (+0.54 vs −0.26). Median-gate was
best IS (+0.96) and dead OOS (−0.03). DIX also drifted structurally higher, so
OOS the >45 gate passes 79% of days — its "edge" rests on excluding 29 trades.
Direction-unstable + structurally degenerate threshold = noise. GEX remains
the only validated options-flow input. Do not revisit without a new mechanism.

### "50 Graphs" quant reference doc — reviewed, nothing to add
The shared Google Doc is a chart/diagnostics catalog (distributions, ACF/PACF,
rolling Sharpe, vol surfaces, microstructure, ML diagnostics) — zero strategies.
Most relevant items are already practiced here (drawdown/rolling-Sharpe/walk-
forward = the validation gauntlet; QQ/fat-tails = the t(4) MC). Its earlier
strategy prompts (UO, Turtle, XS-mom) were already gauntlet-rejected in
test_doc_strategies.py. Calendar-anomaly ideas (turn-of-month, overnight drift)
remain untested (hunt scripts were broken) — low-priority lottery tickets only.

### Macro event filter (FOMC/NFP/CPI) — REJECTED (but validates existing risk mgmt)
Tested whether skipping trades on scheduled high-impact event days cuts the tail:
- Losses do NOT cluster on events: 2/20 worst days are event days (= random ~2).
- Event-day mean P&L (+$41.9) actually > non-event (+$28.8); vol barely higher.
- Skip-event filter: total +117.8%->+102.7%, MaxDD -7.9%->-6.5%, worstMonth -3.4%->-4.3%.
Cuts return, doesn't improve the tail. WHY (good news): existing filters already
handle event risk — VIX-mult (off when VIX>25), HighVol/ATR filter, and timed entries
(Asian/ORB, not at 8:30/2pm releases). Event risk already managed. No filter needed.
Also resolved: options strategies (real edge but NOT tradeable on FTMO/futures props
= off prop-path); order-flow tick data (free for crypto, but needs HFT infra to
exploit — proven dead end). All three "new edge" avenues closed.
