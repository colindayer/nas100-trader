# DAILY HEAD TRADER REVIEW — 2026-08-18

_generated 2026-08-18 20:00 UTC on the trading host_


## Account

- equity **99,430.84** vs anchor **99,944.11** (-0.51%)
- total headroom **9.49%** of 10%
- daily headroom **5.00%** of 5%
- target: **+10.51%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 21892

## What the market offered


**EURUSD** — STRONG_TREND, AT_HTF_LEVEL, RISK_OFF
  - STRONG_TREND: d1 and h4 both up
  - AT_HTF_LEVEL: 0.08 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/up/range, ATR20 0.005112000000000005, range position 120d 0.47693480747236117

**US100.cash** — TRANSITION, COMPRESSION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 transition
  - COMPRESSION: 5d range 0.60x the 20d
  - AT_HTF_LEVEL: 0.11 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/transition/down, ATR20 584.4830000000002, range position 120d 0.8411065489529594

**US500.cash** — WEAK_TREND, COMPRESSION, AT_HTF_LEVEL, RISK_OFF
  - WEAK_TREND: d1 up, h4 transition
  - COMPRESSION: 5d range 0.64x the 20d
  - AT_HTF_LEVEL: 0.02 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/transition/down, ATR20 84.47349999999992, range position 120d 0.9193143145804529

**XAUUSD** — WEAK_TREND, AT_HTF_LEVEL, RISK_OFF
  - WEAK_TREND: d1 up, h4 transition
  - AT_HTF_LEVEL: 0.07 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/transition/down, ATR20 90.13899999999997, range position 120d 0.2733439393426533

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
| BOT_H_gold_sweep_reclaim | SWEEP | 0 | +0.000 | 0% | — | EXPERIMENTAL |

> Every action above is provisional. No bot has the sample to justify promotion or retirement; these are placeholders that will move.

## Shadow desk

| bot::variant | taken | skipped | exp taken | exp skipped | delta |
|---|---|---|---|---|---|
| BOT_F_nas100_vwap_reversion::v2_trend_align | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v3_htf_room | 0 | 1 | None | -1.015 | None |
| BOT_F_nas100_vwap_reversion::v4_low_vol | 1 | 0 | -1.015 | None | None |
| BOT_F_nas100_vwap_reversion::v6_wide_stop | 0 | 1 | None | -1.015 | None |

_A shadow needs many observations before a delta means anything. Promotion requires repeated outperformance, not one good week._

## Coverage — work orders for the Bot Factory

- **STRONG_TREND**: BOT_A_gold_0630_breakout, BOT_B_nas100_usopen_breakout, BOT_C_sp500_london_breakout, BOT_D_gold_ny_breakout, BOT_E_eurusd_london_breakout, BOT_G_nas100_h4_pullback
- **TRANSITION**: BOT_H_gold_sweep_reclaim
- **WEAK_TREND**: BOT_A_gold_0630_breakout, BOT_B_nas100_usopen_breakout, BOT_C_sp500_london_breakout, BOT_D_gold_ny_breakout, BOT_E_eurusd_london_breakout, BOT_G_nas100_h4_pullback

_Every regime observed today has a specialist._

## Probability of passing

**INSUFFICIENT_EVIDENCE** — 6 closed trades. A first-passage estimate needs a stable expectancy and dispersion; computing one from 6 would produce a number with no information in it.

_Raw so far: mean -1.388R over 6, total -8.33R. Descriptive only._

## Patches

See `PATCHES.md` — **0** proposed, none applied.

## Self-critique — would I deploy this desk tomorrow?

- **No.** 6 closed trades, 0/8 bots with any live evidence, and 1 of those trades were structurally invalid rather than informative.
- What I would keep: the risk machinery. Anchors, stop geometry, time exits and the group cap are all now tested, and each was silently broken before.
- What I would not fund: any bot on today's posterior. Every number is prior-dominated.
- What the desk needs: **valid trades, not more code.** The next 20 clean observations decide more than any module I could add.
