# Independent triage of literature_survey_2020_2026.md

_The survey was treated as EXTERNAL and unverified. Verification: citation check
on the #1 paper, cross-check against fresh repo evidence, graveyard comparison._

## Verification findings (why "do not trust without verification" was right)

1. **The #1 citation is real** (Barardehi, Bogousslavsky & Muravyev, RFS 2026;
   SSRN 4069509) — **but the survey stated its mechanism BACKWARDS.** The paper's
   actual finding: portfolios formed on past **INTRADAY** returns display momentum
   (without long-term reversal); **overnight-formed portfolios display NO momentum.**
   The survey claimed "momentum is an overnight phenomenon" — that is the older
   Lou/Polk/Skouras tug-of-war framing, not this paper. Any experiment must use the
   CORRECT signal: the intraday (open-to-close) return component.
2. **The survey is blind to fresh repo evidence**: zero mentions of Part C
   (new_strategy_candidate.md), which already ran canonical TSMOM on 8 ETFs two
   days ago — ETF Sharpe 0.45, **CFD variant killed by financing**. Its #2 ranking
   (industry TSMOM) and every "cost robust ✅ / prop compatible ✅" tag on
   overnight-holding ideas ignore the CFD-financing lesson.
3. Several Tier-2 citations (Salotra 2026, Gao & Yuan SSRN 6112846) are unverified;
   treated as weak until checked.

## Decisions

| Survey rank | Decision | Reason |
|---|---|---|
| #1 Day/Night decomposition | **EXPERIMENT (idea created)** — with the CORRECTED mechanism (intraday-return signal), Alpaca-side only, CFD-financing test mandatory | real RFS paper, free daily OHLC, genuinely distinct from graveyard's unconditional overnight drift AND from validated OVN (calendar) |
| #5 Sector-ETF overnight | **MERGED into #1** as a variant leg | same mechanism family, single unverified paper alone |
| #2 Industry rotation TSMOM | **REJECT for now** | duplicates fresh Part C evidence (monthly trend: CFD-dead, ETF-modest); long-only industry granularity unlikely to overturn it; revisit only if #1 shows the Alpaca sleeve deserves slow strategies |
| #3 Range-based vol timing | **REJECT as experiment** | (a) sizing overlay = frozen production risk surface; (b) survey omitted the key counter-paper: Cederburg et al. 2020 JFE — vol-managed portfolios largely fail out-of-sample; (c) our DD-throttle already occupies this slot. Post-window diagnostic at most |
| #4 Markov optimal window | **REJECT** | adaptive-window = a tuning surface; violates the a-priori-parameter rule; single-lineage literature |
| #6 Factor momentum + regime | **REJECT** | instruments not prop-tradeable; complexity flagged by the survey itself |
| #7 Semivol sizing | **REJECT** | frozen sizing surface; survey itself says low ceiling |
| #8 Momentum crash risk | **REJECT as experiment** | survey itself: "not a new tradeable idea" — reading list only |
| Survey's 11 rejections | **UPHELD** | spot-checked; consistent with FINDINGS graveyard |

## Net result
One idea enters the pipeline: `research/ideas/2026-07-12-intraday-return-momentum-decomposition.md`
(correct mechanism, financing-aware, Alpaca-side). Everything else: rejected or deferred
with reasons. The survey was useful but wrong in exactly the two ways external surveys
are dangerous: a mischaracterized headline mechanism and ignorance of local evidence.
