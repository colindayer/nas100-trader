# FIRST VALID EVIDENCE REPORT — 2026-08-14

_Was every part of 'I observed this market, allocated to this specialist, entered at this time, risked this amount, and earned this R' actually true?_


## Was the desk operational?

- account: **None** None
- AlgoTrading: **None**, connected None
- market engine returned state for **0** symbols

## Attempts

- signals recorded **0**, filled **0**, rejected **0**

## Validity


**BOT_D_gold_ny_breakout** — 2026-08-13T16:30:05+01:00 → **VOID**
  - R -6.070, planned risk $49.97, realised $148.36
  - exit **stop**, holding 0 min
  - state carried: d1 transition, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: h4_regime, h1_regime, ms_labels
  - VOID because: realised risk $148.36 was 3.0x the planned $49.97

**BOT_F_nas100_vwap_reversion** — 2026-08-13T16:07:02+01:00 → **VOID**
  - R -0.970, planned risk $49.74, realised $48.15
  - exit **stop**, holding 87 min
  - state carried: d1 transition, h4 up, h1 None, labels None
  - VOID because: missing mandatory state: h1_regime, ms_labels

## Verdict

- **0** valid observation(s) today, 2 void.
- The desk has still not produced a trustworthy observation.

### What the desk learned about EXECUTION
- nothing: no fills.

### What the desk learned about MARKET BEHAVIOUR
- nothing that generalises — n=0 is not a sample. Recorded, not interpreted.

### What remains unknown
- whether any specialist has an edge. No bot has the observations to say.

## Recommendation

**FIX A PROVEN DEFECT** — missing mandatory state: h4_regime, h1_regime, ms_labels
