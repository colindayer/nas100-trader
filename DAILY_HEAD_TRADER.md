# DAILY HEAD TRADER REVIEW — 2026-09-05

_generated 2026-09-05 20:00 UTC on the trading host_


## Account

- equity **99,995.90** vs anchor **99,944.11** (+0.05%)
- total headroom **10.05%** of 10%
- daily headroom **5.00%** of 5%
- target: **+9.95%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 22040

## What the market offered


**EURUSD** — WEAK_TREND, AT_HTF_LEVEL, RISK_OFF
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.01 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/transition/transition, ATR20 0.004405999999999977, range position 120d 0.5507052992756407

**US100.cash** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.00 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 376.79749999999933, range position 120d 0.8416956188241662

**US500.cash** — TRANSITION, AT_HTF_LEVEL, RISK_ON
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.01 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 59.21499999999996, range position 120d 0.9287461448473893

**XAUUSD** — TRANSITION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - AT_HTF_LEVEL: 0.00 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/transition, ATR20 106.35099999999989, range position 120d 0.5133412689216382

## Today's trades (0)

_no trades closed today_

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
| BOT_H_gold_sweep_reclaim | SWEEP | 2 | +0.024 | 17% | 0.000 | KEEP |

> Every action above is provisional. No bot has the sample to justify promotion or retirement; these are placeholders that will move.

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_H_gold_sweep_reclaim::v3_htf_room | 1 | 1 | 1.293 | -1.009 | 1.151 |
| BOT_H_gold_sweep_reclaim::v6_wide_stop | 1 | 1 | 1.293 | -1.009 | 1.151 |
| BOT_H_gold_sweep_reclaim::v2_trend_align | 1 | 1 | -1.009 | 1.293 | -1.151 |
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |
| BOT_H_gold_sweep_reclaim::v4_vol_expansion | 2 | 0 | 0.142 | None | None |
| BOT_H_gold_sweep_reclaim::v5_clean_break | 0 | 0 | None | None | None |
| BOT_H_gold_sweep_reclaim::v7_not_extended | 2 | 0 | 0.142 | None | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **TRANSITION**: BOT_H_gold_sweep_reclaim
- **WEAK_TREND**: BOT_A_gold_0630_breakout, BOT_B_nas100_usopen_breakout, BOT_C_sp500_london_breakout, BOT_D_gold_ny_breakout, BOT_E_eurusd_london_breakout, BOT_G_nas100_h4_pullback

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 8 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 8 would produce a number with no information in it.

_Raw so far: mean -1.005R over 8, total -8.04R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 8 closed trades, 1/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
