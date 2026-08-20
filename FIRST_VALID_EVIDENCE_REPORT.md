# FIRST VALID EVIDENCE REPORT — 2026-08-20

_Was every part of 'I observed this market, allocated to this specialist, entered at this time, risked this amount, and earned this R' actually true?_


## Was the desk operational?

- account: **1514166963** FTMO-Demo
- AlgoTrading: **True**, connected True
- market engine returned state for **4** symbols

## Attempts

- signals recorded **0**, filled **0**, rejected **0**

## Validity


**BOT_E_eurusd_london_breakout** — 2026-08-12T12:04:00+01:00 → **VOID**
  - R -1.361, planned risk $49.98, realised $68.00
  - exit **stop**, holding 5 min
  - state carried: d1 None, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels

**BOT_B_nas100_usopen_breakout** — 2026-08-12T16:02:00+01:00 → **VOID**
  - R -1.001, planned risk $99.90, realised $100.01
  - exit **stop**, holding 12 min
  - state carried: d1 None, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels

**BOT_D_gold_ny_breakout** — 2026-08-12T16:30:00+01:00 → **VOID**
  - R -2.976, planned risk $49.93, realised $148.60
  - exit **time_or_manual**, holding 0 min
  - state carried: d1 None, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels
  - VOID because: realised risk $148.60 was 3.0x the planned $49.93

**BOT_F_nas100_vwap_reversion** — 2026-08-12T16:33:00+01:00 → **VOID**
  - R -0.988, planned risk $49.83, realised $49.26
  - exit **stop**, holding 1 min
  - state carried: d1 None, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels

**BOT_A_gold_0630_breakout** — 2026-08-12T11:12:00+01:00 → **VOID**
  - R -0.984, planned risk $99.94, realised $98.37
  - exit **stop**, holding 1388 min
  - state carried: d1 None, h4 None, h1 None, labels None
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels

**BOT_F_nas100_vwap_reversion** — 2026-08-13T18:07:00+01:00 → **VOID**
  - R -1.015, planned risk $47.45, realised $48.15
  - exit **stop**, holding 27 min
  - state carried: d1 None, h4 None, h1 None, labels ['TREND_UP', 'RANGE', 'MID_VOL', 'VOL_CONTRACTING', 'NEAR_HTF_RESISTANCE', 'NEAR_HTF_SUPPORT']
  - VOID because: missing mandatory state: d1_regime, h4_regime, h1_regime

## Verdict

- **0** valid observation(s) today, 6 void.
- The desk has still not produced a trustworthy observation.

### What the desk learned about EXECUTION
- nothing: no fills.

### What the desk learned about MARKET BEHAVIOUR
- nothing that generalises — n=0 is not a sample. Recorded, not interpreted.

### What remains unknown
- whether any specialist has an edge. No bot has the observations to say.

## Recommendation

**FIX A PROVEN DEFECT** — missing mandatory state: d1_regime, h4_regime, h1_regime, atr20_d1, ms_labels
