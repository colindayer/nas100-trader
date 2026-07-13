# ALPHA LEAK AUDIT — implementation drift across the 8 strategies

_2026-07-13. Chief Research Auditor forensic pass. Read-only; no code/strategy/param
change. Question answered: where does the LIVE system diverge from the VALIDATED
research, and how much expectancy does each divergence probably cost? All impact
figures are ESTIMATES with stated confidence; the live sample is ~0 clean trades, so
these are prospective haircuts to the validated numbers, not measured live deltas.
Evidence cited from this repo's audits._

## Method
The validated numbers (e.g. S5 Sharpe 0.88, +0.43 avg R) were produced by
`master_backtest.py` / `full_yearly.py` on **ETF hourly history**, filling at the
signal-bar Close, with **3 bps/side** cost, **no commission, no financing, no regime
throttle**. Production (`live_trader.py`) differs in the ways below. Each row estimates
the impact of ONE divergence.

---

## RANKED FINDINGS — highest expected live impact first

| # | Finding | Scope | Δ Expectancy | Δ Sharpe | Δ Frequency | Conf | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | **Live risk overlay not in validated backtest** — sizing multiplies `vix_mult × RISK_SCALE × DD-throttle`; validated sizing is raw `risk/stop`. `vix_mult=0` drops trades entirely. | ALL | neutral-to-negative on raw return; throttle lowers both tails | **−0.05 to −0.20** on raw; may *raise* risk-adjusted | **−10–40%** when VIX gate bites | HIGH | live_trader `shares=…*vix_mult*RISK_SCALE`; backtest `(cap*RISK)/(price*STOP)` |
| 2 | **CFD financing on MT5 not in ETF backtest** — ~3 bps/day on notional, **triple on weekends**; a bracket held ~2–3 days pays ~6–9 bps/trade the backtest never saw. | S1,S2,S4,S5,BTC,OVN on MT5 | **−0.06 to −0.10 R/trade** | −0.05 to −0.15 | none | HIGH | full_yearly cost note (ETF, no financing); FINDINGS CFD-financing law (confirmed 4×) |
| 3 | **ETF-validated edge traded on CFD** — QQQ/SPY/GLD→US100/US500/XAUUSD: different instrument, ~23h continuous vs cash session, different spread/point value. The edge was never validated on this feed. | S1,S3,S4,S5 (MT5 side) | **−0.05 to −0.15 R** (unmodeled) | −0.10 to −0.25 | ± | MED | STRATEGY_VALIDATION_AUDIT (S5 CFD premise); venue rows |
| 4 | **S5 ORB uses the 9:00 hourly bar, not the 9:30 cash opening range / no CFD auction** — the "opening range" premise is mis-defined vs the validated ORB literature. | S5 | **−0.10 to −0.20 R** if premise weak | −0.15 to −0.30 | ± | MED | live_trader `or_bar=hour==9`; VALIDATION_AUDIT (PARTIAL-CFD) |
| 5 | **S3 rule drift** — live rule (z>1.5 & ret>1%) is a strict SUBSET of the validated (vol>1.3×MA20 & green): ~4/yr vs ~15/yr. 73% of validated signals never trade. | S3 | edge/trade preserved (subset) | ~0 per trade | **−73%** | HIGH | STRATEGY_VALIDATION_AUDIT (measured on identical data) |
| 6 | **Market-order-after-bar-close vs backtest fill-at-signal-close** — backtest transacts at the exact Close that generated the signal; live sends a MARKET order on the next tick → half-spread + adverse selection beyond the modeled 3 bps. | ALL | **−0.02 to −0.05 R** | −0.03 to −0.08 | none | MED | mt5_broker TRADE_ACTION_DEAL; backtest fills at Close |
| 7 | **DST / session-boundary fragility on MT5** — session gates are fixed ET wall-clock hours (2–5, 9–12, 9:00 ORB, 16:00 close); MT5 bars are server-time via offset detection. A missed DST shift moves every session window ~1h twice/yr. | S1,S2,S3,S4,S5 on MT5 | spikes on DST weeks | episodic | wrong-window trades | MED | live_trader fixed `hour==` gates; mt5 offset auto-detect |
| 8 | **Weekend financing + gap on CFD holds** — brackets held over Friday pay triple swap and eat the Fri→Mon gap; ETF backtest paid neither. (S5 net-benefits from weekend *direction*, but still pays the CFD carry.) | S5,S1,S2,OVN | **−0.02 to −0.06 R** on weekend-held | small | none | MED-HIGH | WEEKEND_EXPOSURE_AUDIT (gap edge vs financing) |
| 9 | **BTC venue swap** — validated on Binance spot, traded on Pepperstone CFD: basis, wider spread, CFD financing vs spot funding. | BTC | **−0.05 to −0.15 R** (unmeasured) | −0.1 to −0.2 | ± | LOW-MED | VALIDATION_AUDIT (venue caveat) |
| 10 | **S3 on MT5 has no time-exit / no target** — the 5-day/2% exit path is Alpaca-only; on MT5 an S3 position has no defined exit. | S3 (MT5) | tail risk, not steady drag | high-variance | none | HIGH | CURRENT_PROJECT_STATE blocker #3 |
| 11 | **S5 same-day re-entry** — live re-enters after a stop; backtest takes ≤1/day. | S5 | **+0.00 (breakeven)** | −0.01 | +1.6/yr | HIGH | S5_REENTRY_REVIEW (quantified, accepted) |
| 12 | **BTCTREND/XSMOM no broker stop** — rebalance-managed; a gap can exceed the intended risk. | BTCTREND | risk leak, not cost | tail | none | HIGH | CURRENT_PROJECT_STATE blocker #5 |
| 13 | **Commission not modeled** — Pepperstone raw ~$3.5/lot/side; ETF backtest is commission-free. | MT5 strategies | **−0.005 to −0.02 R** | small | none | MED | full_yearly "Alpaca commission-free" |

---

## ALPHA LEAK REPORT — where expectancy is most probably lost

**The dominant leak is not any single strategy — it is that the validated numbers were
measured in a world the live system does not trade in.** Ranked by probable total
expectancy lost:

1. **The unmodeled cost + throttle stack on the CFD (MT5) path (#1,#2,#3,#6,#8,#13).**
   Stacked, these plausibly convert a validated ~0.9 Sharpe / +0.43 R strategy into a
   live ~0.5–0.65 Sharpe / +0.30–0.35 R one — **a 25–40% haircut** before any strategy
   is "wrong." Financing + market-order slippage + CFD spread + the vix/DD throttle
   each take 5–15%; they compound. **This is where the most edge is silently going.**
2. **S3 frequency starvation (#5).** Not a per-trade leak but a ~73% *volume* leak —
   the strategy is running at ~27% of its validated trade count, so ~73% of its
   contribution to the book is simply absent.
3. **S5 ORB mis-definition on CFD (#4).** If the 9:00-bar premise is genuinely weaker
   than the validated opening range, S5 is the single largest per-strategy edge risk.
4. **DST/session fragility (#7)** — a rare but total leak: on a mishandled DST week the
   strategies trade the wrong hours entirely.

**Gap attribution (best estimate of the backtest→live shortfall):**
~40–55% cost/financing/slippage stack · ~20–30% throttle-and-frequency (S3 + vix gate)
· ~15–25% instrument/venue mismatch (CFD, BTC) · ~5–10% episodic (DST, weekend tails).

---

## RECOMMENDATIONS — parity restoration ONLY (no new indicators, no optimization)

All are post-window (any signal-touching change resets the clock; committee 2026-08-16).
Ordered by expected recovered edge per unit of effort.

1. **Re-validate every strategy with the REAL cost stack.** Re-run the gauntlet with
   CFD spread + commission + ~3 bps/day financing (weekend ×3) for the MT5 path, ETF
   costs for the Alpaca path. This changes NO production code — it corrects the
   *expectation* so the committee compares live against an honest baseline, not an
   ETF-costed fantasy. Recovers no edge but stops mis-attributing the haircut to "dead
   strategy." **Highest priority, zero risk.**
2. **Route each strategy to the venue it was validated on.** The edge was validated on
   ETF; where an ETF venue exists (Alpaca: S1/S3/S4/S5 on QQQ/SPY), prefer it — it has
   **no financing** and matches the validated instrument. Use MT5 CFD only where it is
   the only venue (index/gold/BTC for the prop challenge) and accept the measured cost.
3. **Restore S3's validated rule** (revert the un-validated z-score tightening to
   vol>1.3×MA20 & green). Pure parity restoration; recovers ~73% of S3's frequency.
   Already flagged; human deferred KEEP-AS-IS to committee — re-surface with the cost
   re-validation.
4. **Fix S5's opening-range definition to the validated one** (actual 9:30 cash
   open / true opening range), or explicitly retire S5 on the CFD where no auction
   exists. Parity, not optimization.
5. **Harden the MT5 session offset for DST** — derive the ET session boundaries from a
   DST-aware conversion, not a fixed detected offset. Removes the twice-yearly total leak.
6. **Consider limit-at-signal-price instead of market-after-close** for entries, to
   approach the backtest's fill assumption — but MEASURE first via the existing fill
   ledger (partial-fill risk); do not assume.
7. **Give S3-on-MT5 and BTCTREND real broker-side exits/stops** — parity with the
   validated exit logic and removes the uncapped-tail risk (#10, #12).

**Explicitly NOT recommended:** new indicators, parameter tuning, new strategies, or
any change that "improves" a validated number. The task is to recover the edge that
already passed validation and is leaking on the way to the broker — nothing more.

---

## The one-line finding
The strategies are probably closer to their validated edge than they look; **most of
the apparent weakness is an ETF-validated book being traded through a CFD cost stack
and a live risk throttle that the backtest never modeled.** Fix the measurement first
(re-validate with real costs), route to the validated venue second, restore S3/S5
parity third — in that order, after the window.
