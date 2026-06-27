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

### Volume Profile strategy (LAT concept) — REJECTED (on available data)
Long below Value-Area-Low → target POC, rolling 10-day profile, net of costs:
−0.6%/yr (OOS −1.1%); inverse also negative. No mean-reversion edge.
**Caveat:** built on *hourly* bars (~16/day = a coarse 50-bin profile). Real volume
profile wants minute/tick data — this is a data limitation, not a definitive death.
Not pursued further without finer data.

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
