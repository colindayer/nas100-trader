# DAILY HEAD TRADER REVIEW — 2026-09-09

_generated 2026-09-09 20:00 UTC on the trading host_


## Account

- equity **99,980.93** vs anchor **99,944.11** (+0.04%)
- total headroom **10.04%** of 10%
- daily headroom **4.99%** of 5%
- target: **+9.96%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 21265

## What the market offered


**EURUSD** — WEAK_TREND, AT_HTF_LEVEL, RISK_OFF
  - WEAK_TREND: d1 up, h4 range
  - AT_HTF_LEVEL: 0.10 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/range/range, ATR20 0.004476999999999976, range position 120d 0.5846359130766299

**US100.cash** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.09 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/down, ATR20 370.40249999999924, range position 120d 0.833649175051512

**US500.cash** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.28 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/down, ATR20 58.636499999999934, range position 120d 0.882690364777199

**XAUUSD** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 down
  - AT_HTF_LEVEL: 0.02 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/down/transition, ATR20 105.98399999999988, range position 120d 0.481749902560807

## Today's trades (1)


### BOT_H_gold_sweep_reclaim — 2026-09-09T16:16:02+01:00
| | |
|---|---|
| side | SHORT |
| entry / stop / target | 4388.56 / 4429.8576 / 4282.576000000001 |
| exit / outcome | 4403.46 / time_or_manual |
| gross / swap / comm / net | -14.91 / 0.0 / -0.06 / **-14.969999999999999** |
| R | **-0.362** |
| MFE / MAE | 0.2990488551392914 / -0.7915714230366825 R |
| holding | 224 min |
| spread / slippage | 0.4499999999998181 / None |
| regime at entry | transition d1, down h4 |
| macro | RISK_OFF, None |
| shadows | {"v2_trend_align": true, "v3_htf_room": false, "v4_vol_expansion": false, "v5_clean_break": null, "v6_wide_stop": true, "v7_not_extended": true} |

**Diagnosis: EXPECTED_LOSS** — R -0.362, no anomaly detected

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
| BOT_H_gold_sweep_reclaim | SWEEP | 3 | -0.006 | 23% | 0.000 | KEEP |

> Every action above is provisional. No bot has the sample to justify promotion or retirement; these are placeholders that will move.

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_H_gold_sweep_reclaim::v3_htf_room | 1 | 2 | 1.293 | -0.686 | 1.319 |
| BOT_H_gold_sweep_reclaim::v6_wide_stop | 2 | 1 | 0.465 | -1.009 | 0.492 |
| BOT_H_gold_sweep_reclaim::v4_vol_expansion | 2 | 1 | 0.142 | -0.362 | 0.168 |
| BOT_H_gold_sweep_reclaim::v2_trend_align | 2 | 1 | -0.686 | 1.293 | -0.66 |
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |
| BOT_H_gold_sweep_reclaim::v5_clean_break | 0 | 0 | None | None | None |
| BOT_H_gold_sweep_reclaim::v7_not_extended | 3 | 0 | -0.026 | None | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **TRANSITION**: BOT_H_gold_sweep_reclaim
- **WEAK_TREND**: BOT_A_gold_0630_breakout, BOT_B_nas100_usopen_breakout, BOT_C_sp500_london_breakout, BOT_D_gold_ny_breakout, BOT_E_eurusd_london_breakout, BOT_G_nas100_h4_pullback

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 9 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 9 would produce a number with no information in it.

_Raw so far: mean -0.934R over 9, total -8.40R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 9 closed trades, 1/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
