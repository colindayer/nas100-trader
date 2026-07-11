# MACRO REGIME SURVEY — filters for hourly-daily systematic trading

_Head-of-Research literature review, 2026-07-11. Scope: macro regime gates that
could sit alongside our existing regime layer (VIX 21d-MA multiplier, SPY golden
cross, QQQ 200d SMA, GEX sign). Bar for an "idea": systematic rule + free data +
daily-or-faster signal + plausibly additive to what we already gate on.
Production untouched; survivors enter the normal pipeline (graveyard check ->
experiment -> gauntlet)._

## Reviewed candidates

### 1. VIX term structure (contango/backwardation) — STRONGEST
- **Paper:** Fassas & Hourvouliades, "VIX Futures as a Market Timing Indicator"
  (SSRN 3189502; also MDPI JRFM 2019).
- **Hypothesis:** the slope of the VIX futures curve prices forward risk;
  backwardation (inverted curve) marks stress that is contrarian-bullish for
  subsequent S&P returns; contango = normal risk-on carry regime.
- **Rule:** signal = VIX3M/VIX ratio (or front-basis). Ratio > 1 (contango) =
  risk-on regime; < 1 (backwardation) = stress. Daily close, no optimization.
- **Data:** ^VIX and ^VIX3M — **free via yfinance**, back to 2010+.
- **Systematic:** yes, one ratio, a-priori threshold at 1.0.
- **Testable free:** yes, trivially.
- **Research OS fit:** perfect — same shape as our existing `vix_mult` gate;
  test = does gating S1/S4/S5 on term-structure beat gating on VIX level alone.
- **Caveat:** correlated with our VIX-level gate (ratio and level co-move);
  the gauntlet must show *incremental* value, else reject.

### 2. Credit spreads / Excess Bond Premium — ROBUST BUT SLOW
- **Paper:** Gilchrist & Zakrajšek, "Credit Spreads and Business Cycle
  Fluctuations" (AER 2012); Fed EBP updates (FEDS Notes).
- **Hypothesis:** the non-default component of corporate spreads (EBP) measures
  financial-sector risk appetite and predicts downturns 1-4 quarters ahead.
- **Rule (practitioner adaptation):** risk-off when EBP > 0 (or HY OAS above
  its 200d MA). Monthly (EBP) or daily (HY OAS via FRED `BAMLH0A0HYM2`).
- **Data:** FRED, free. EBP monthly + revised; HY OAS daily, unrevised.
- **Systematic:** yes. **Testable free:** yes (HY OAS variant).
- **OS fit:** good as a *sizing* regime (like vix_mult), but quarterly-horizon
  predictor gating ~11-trades/yr strategies = very few independent regime
  switches in any test window -> hard to clear ">=30 obs" honestly.
- **Verdict:** paper note kept; idea deferred until the book trades daily-plus
  frequency where a slow gate has enough switches to validate.

### 3. Fed net liquidity (WALCL − TGA − RRP) — POPULAR, WEAK PROVENANCE
- **Source:** practitioner only (Max Anderson "net liquidity fair value";
  TradingView indicators; no peer-reviewed strategy paper found).
- **Hypothesis:** post-2008 equity beta to central-bank liquidity.
- **Rule:** rising net-liquidity 4-week change = risk-on.
- **Data:** FRED WALCL/WTREGEN/RRPONTSYD, free, weekly.
- **Systematic:** yes. **Testable free:** yes.
- **OS fit:** weekly signal, essentially ONE regime (2009-2021 QE) driving the
  whole in-sample story — textbook regime-dependent illusion our gauntlet
  exists to kill (IS Sharpe>0 in BOTH halves will likely fail).
- **Verdict:** rejected at review — no idea created. Logged here as graveyard-adjacent.

### 4. Market breadth (% above 200dMA, 52wk highs-lows) — REDUNDANT FOR US
- **Source:** practitioner literature (CMT/StockCharts; Vince & Williams "Ripple
  Effect of Daily New Lows"); no strong academic strategy paper for *gating*.
- **Rule:** risk-on when NYSE % above 200dMA > 50% (or NH-NL > 0).
- **Data:** free-ish (some breadth series need paid feeds; % above MA computable
  from constituent data we do not hold).
- **OS fit:** we trade ONE index complex (NAS100/QQQ). Breadth of the index vs
  the index's own 200d SMA (already a gate) adds little; constituent data cost
  breaks the free-data rule. **Rejected — no idea.**

### 5. Yield curve (10y-2y / 10y-3m) — WRONG FREQUENCY
- **Paper lineage:** Estrella & Mishkin (recession prediction); recent updates.
- Predicts recessions 6-18 months out. Gating hourly strategies on a signal with
  ~2 regime flips per decade cannot be validated at our sample sizes.
  **Rejected — no idea.**

### 6. Treasury rate momentum / DXY — WEAK EVIDENCE AS EQUITY GATES
- Rate-of-change filters on 10y yields and dollar-index trend appear in
  practitioner momentum literature; as *equity regime gates* the published
  evidence is thin and unstable across decades (dollar-equity correlation flips
  sign by regime). **Rejected — no idea.**

## Ranking (robustness x complexity x expected research value)

| Rank | Idea | Robustness | Complexity | Research value | Action |
|---|---|---|---|---|---|
| 1 | VIX term structure ratio gate (VIX3M/VIX) | high (academic + economic mechanism) | trivial (2 yfinance tickers, 1 ratio) | HIGH — direct upgrade candidate for the existing vix_mult gate | **idea created** |
| 2 | HY-OAS / EBP credit regime | high (AER-grade) | low (FRED) | medium — frequency mismatch with our sparse book | paper note only |
| 3 | Fed net liquidity | low (one-regime story) | low | low | rejected |
| 4 | Breadth | medium | medium (data cost) | low (redundant) | rejected |
| 5 | Yield curve | high for recessions | trivial | ~zero at our frequency | rejected |
| 6 | Rates/DXY momentum gates | low | low | low | rejected |

## Artifacts created
- `research/papers/vix-futures-as-a-market-timing-indicator-fassas-2019.md`
- `research/papers/credit-spreads-and-business-cycle-fluctuations-gz-2012.md`
- `research/ideas/2026-07-11-vix-term-structure-regime-gate.md` (the sole survivor)

## Sources
- [Fassas & Hourvouliades — VIX Futures as a Market Timing Indicator (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3189502) · [MDPI version](https://www.mdpi.com/1911-8074/12/3/113)
- [Quantpedia — Exploiting Term Structure of VIX Futures](https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures)
- [Gilchrist & Zakrajšek — Credit Spreads and Business Cycle Fluctuations (AER)](https://www.aeaweb.org/articles?id=10.1257%2Faer.102.4.1692) · [NBER w17021](https://www.nber.org/papers/w17021)
- [Fed — Recession Risk and the Excess Bond Premium](https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html) · [EBP update](https://www.federalreserve.gov/econres/notes/feds-notes/updating-the-recession-risk-and-the-excess-bond-premium-20161006.html)
- [PreReason — Net Liquidity Formula](https://www.prereason.com/insights/net-liquidity) · [TradingView net-liquidity indicator](https://www.tradingview.com/script/AWrUtm2d-FED-Net-Liquidity-WALCL-TGA-RRP/)
- [Vince & Williams — Ripple Effect of Daily New Lows (CMT)](https://cmtassociation.org/wp-content/uploads/2024/06/the-ripple-effect-of-daily-new-lows-by-ralph-vince-and-larry-williams.pdf)
