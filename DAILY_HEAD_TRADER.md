# DAILY HEAD TRADER REVIEW — 2026-09-11

_generated 2026-09-11 20:00 UTC on the trading host_


## Account

- equity **99,882.25** vs anchor **99,944.11** (-0.06%)
- total headroom **9.94%** of 10%
- daily headroom **4.95%** of 5%
- target: **+10.06%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 39327

## What the market offered


**EURUSD** — TRANSITION, AT_HTF_LEVEL, RISK_ON
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.07 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 0.004512499999999986, range position 120d 0.5186808997331297

**US100.cash** — TRANSITION, AT_HTF_LEVEL, RISK_ON
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.30 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 365.39799999999923, range position 120d 0.8251640622258319

**US500.cash** — TRANSITION, AT_HTF_LEVEL, RISK_ON
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.10 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: transition/transition/up, ATR20 59.88899999999994, range position 120d 0.8924611826012975

**XAUUSD** — TRANSITION, AT_HTF_LEVEL, RISK_ON
  - TRANSITION: d1 unconfirmed, h4 down
  - AT_HTF_LEVEL: 0.02 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: transition/down/transition, ATR20 107.40299999999984, range position 120d 0.4293328838840847

## Today's trades (1)


### BOT_H_gold_sweep_reclaim — 2026-09-11T10:02:02+01:00
| | |
|---|---|
| side | LONG |
| entry / stop / target | 4353.24 / 4329.33955 / 4460.643 |
| exit / outcome | 4329.18 / stop |
| gross / swap / comm / net | -48.12 / 0.0 / -0.12 / **-48.24** |
| R | **-1.009** |
| MFE / MAE | 0.0 / -0.9665089987845151 R |
| holding | 182 min |
| spread / slippage | 0.4499999999998181 / None |
| regime at entry | transition d1, down h4 |
| macro | RISK_ON, None |
| shadows | {"v2_trend_align": false, "v3_htf_room": false, "v4_vol_expansion": false, "v5_clean_break": null, "v6_wide_stop": false, "v7_not_extended": true} |

**Diagnosis: EXPECTED_LOSS** — R -1.009, no anomaly detected

## Risk overruns (0)

_none — every loss stayed inside its planned risk_

## Bot scoreboard

| bot | playbook | n | posterior R | conf | exec slip/R | action |
|---|---|---|---|---|---|---|
| BOT_A_gold_0630_breakout | BREAKOUT | 0 | +0.150 | 0% | — | EXPERIMENTAL |
| BOT_B_nas100_usopen_breakout | BREAKOUT | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_C_sp500_london_breakout | BREAKOUT | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_D_gold_ny_breakout | BREAKOUT | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_E_eurusd_london_breakout | BREAKOUT | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_F_nas100_vwap_reversion | REVERSION | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_G_nas100_h4_pullback | CONTINUATION | 0 | +0.000 | 0% | — | EXPERIMENTAL |
| BOT_H_gold_sweep_reclaim | SWEEP | 5 | -0.141 | 33% | 0.000 | KEEP |

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_H_gold_sweep_reclaim::v3_htf_room | 1 | 4 | 1.293 | -0.851 | 1.715 |
| BOT_H_gold_sweep_reclaim::v6_wide_stop | 2 | 3 | 0.465 | -1.013 | 0.887 |
| BOT_H_gold_sweep_reclaim::v4_vol_expansion | 2 | 3 | 0.142 | -0.798 | 0.564 |
| BOT_H_gold_sweep_reclaim::v2_trend_align | 2 | 3 | -0.686 | -0.246 | -0.264 |
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |
| BOT_H_gold_sweep_reclaim::v5_clean_break | 0 | 0 | None | None | None |
| BOT_H_gold_sweep_reclaim::v7_not_extended | 5 | 0 | -0.422 | None | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **TRANSITION**: BOT_H_gold_sweep_reclaim

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 11 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 11 would produce a number with no information in it.

_Raw so far: mean -0.949R over 11, total -10.43R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 11 closed trades, 1/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
