# DAILY HEAD TRADER REVIEW — 2026-09-03

_generated 2026-09-03 20:00 UTC on the trading host_


## Account

- equity **99,953.66** vs anchor **99,944.11** (+0.01%)
- total headroom **10.01%** of 10%
- daily headroom **5.00%** of 5%
- target: **+9.99%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 21064

## What the market offered


**EURUSD** — WEAK_TREND, AT_HTF_LEVEL, RISK_ON
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.26 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: up/transition/up, ATR20 0.00441649999999999, range position 120d 0.5813953488372093

**US100.cash** — WEAK_TREND, AT_HTF_LEVEL, RISK_ON
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.13 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: up/transition/up, ATR20 383.53799999999956, range position 120d 0.840555079286298

**US500.cash** — WEAK_TREND, AT_HTF_LEVEL, RISK_ON
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.04 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: up/transition/up, ATR20 56.9, range position 120d 0.9538112836328833

**XAUUSD** — WEAK_TREND, AT_HTF_LEVEL, RISK_ON
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.33 ATR to a level
  - RISK_ON: macro_risk
  - regimes d1/h4/h1: up/transition/up, ATR20 104.7514999999999, range position 120d 0.4971657808762348

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
| BOT_H_gold_sweep_reclaim | SWEEP | 1 | -0.092 | 9% | 0.000 | KEEP |

> Every action above is provisional. No bot has the sample to justify promotion or retirement; these are placeholders that will move.

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |
| BOT_H_gold_sweep_reclaim::v2_trend_align | 1 | 0 | -1.009 | None | None |
| BOT_H_gold_sweep_reclaim::v3_htf_room | 0 | 1 | None | -1.009 | None |
| BOT_H_gold_sweep_reclaim::v4_vol_expansion | 1 | 0 | -1.009 | None | None |
| BOT_H_gold_sweep_reclaim::v5_clean_break | 0 | 0 | None | None | None |
| BOT_H_gold_sweep_reclaim::v6_wide_stop | 0 | 1 | None | -1.009 | None |
| BOT_H_gold_sweep_reclaim::v7_not_extended | 1 | 0 | -1.009 | None | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **WEAK_TREND**: BOT_A_gold_0630_breakout, BOT_B_nas100_usopen_breakout, BOT_C_sp500_london_breakout, BOT_D_gold_ny_breakout, BOT_E_eurusd_london_breakout, BOT_G_nas100_h4_pullback

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 7 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 7 would produce a number with no information in it.

_Raw so far: mean -1.334R over 7, total -9.33R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 7 closed trades, 1/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
