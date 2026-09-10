# DAILY HEAD TRADER REVIEW — 2026-09-10

_generated 2026-09-10 20:00 UTC on the trading host_


## Account

- equity **99,930.49** vs anchor **99,944.11** (-0.01%)
- total headroom **9.99%** of 10%
- daily headroom **4.95%** of 5%
- target: **+10.01%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 28093

## What the market offered


**EURUSD** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.23 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 0.00443199999999998, range position 120d 0.5440335493709499

**US100.cash** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.29 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/down, ATR20 366.7549999999992, range position 120d 0.7948206971579257

**US500.cash** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 down
  - AT_HTF_LEVEL: 0.22 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/down/down, ATR20 59.48899999999994, range position 120d 0.8514503349994684

**XAUUSD** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 down
  - AT_HTF_LEVEL: 0.00 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/down/down, ATR20 106.67549999999987, range position 120d 0.4030401028115162

## Today's trades (1)


### BOT_H_gold_sweep_reclaim — 2026-09-10T11:16:02+01:00
| | |
|---|---|
| side | LONG |
| entry / stop / target | 4398.53 / 4373.838675 / 4505.2055 |
| exit / outcome | 4373.37 / stop |
| gross / swap / comm / net | -50.32 / 0.0 / -0.12 / **-50.440000000000005** |
| R | **-1.021** |
| MFE / MAE | 0.05265007041947702 / -0.9756463049269475 R |
| holding | 104 min |
| spread / slippage | 0.4499999999998181 / None |
| regime at entry | transition d1, down h4 |
| macro | RISK_OFF, None |
| shadows | {"v2_trend_align": false, "v3_htf_room": false, "v4_vol_expansion": false, "v5_clean_break": null, "v6_wide_stop": false, "v7_not_extended": true} |

**Diagnosis: EXPECTED_LOSS** — R -1.021, no anomaly detected

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
| BOT_H_gold_sweep_reclaim | SWEEP | 4 | -0.079 | 29% | 0.000 | KEEP |

> Every action above is provisional. No bot has the sample to justify promotion or retirement; these are placeholders that will move.

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_H_gold_sweep_reclaim::v3_htf_room | 1 | 3 | 1.293 | -0.798 | 1.568 |
| BOT_H_gold_sweep_reclaim::v6_wide_stop | 2 | 2 | 0.465 | -1.015 | 0.74 |
| BOT_H_gold_sweep_reclaim::v4_vol_expansion | 2 | 2 | 0.142 | -0.692 | 0.417 |
| BOT_H_gold_sweep_reclaim::v2_trend_align | 2 | 2 | -0.686 | 0.136 | -0.411 |
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |
| BOT_H_gold_sweep_reclaim::v5_clean_break | 0 | 0 | None | None | None |
| BOT_H_gold_sweep_reclaim::v7_not_extended | 4 | 0 | -0.275 | None | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **TRANSITION**: BOT_H_gold_sweep_reclaim

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 10 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 10 would produce a number with no information in it.

_Raw so far: mean -0.943R over 10, total -9.43R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 10 closed trades, 1/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
