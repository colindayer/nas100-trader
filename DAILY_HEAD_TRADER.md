# DAILY HEAD TRADER REVIEW — 2026-08-17

_generated 2026-08-17 20:00 UTC on the trading host_


## Account

- equity **99,431.72** vs anchor **99,944.11** (-0.51%)
- total headroom **9.49%** of 10%
- daily headroom **5.00%** of 5%
- target: **+10.51%** remaining to +10%
- terminal: trade_allowed **True**, connected True, ping 35345

## What the market offered


**EURUSD** — STRONG_TREND, COMPRESSION, AT_HTF_LEVEL, RISK_OFF
  - STRONG_TREND: d1 and h4 both up
  - COMPRESSION: 5d range 0.71x the 20d
  - AT_HTF_LEVEL: 0.05 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/up/transition, ATR20 0.005079999999999996, range position 120d 0.48513152878383525

**US100.cash** — TRANSITION, COMPRESSION, AT_HTF_LEVEL, RISK_OFF
  - TRANSITION: d1 unconfirmed, h4 up
  - COMPRESSION: 5d range 0.58x the 20d
  - AT_HTF_LEVEL: 0.03 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: transition/up/transition, ATR20 594.583, range position 120d 0.9042748925887487

**US500.cash** — WEAK_TREND, COMPRESSION, AT_HTF_LEVEL, RISK_OFF
  - WEAK_TREND: d1 up, h4 transition
  - COMPRESSION: 5d range 0.57x the 20d
  - AT_HTF_LEVEL: 0.01 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/transition/down, ATR20 85.12099999999995, range position 120d 0.95334600659364

**XAUUSD** — STRONG_TREND, EXTENDED, AT_HTF_LEVEL, RISK_OFF
  - STRONG_TREND: d1 and h4 both up
  - EXTENDED: +2.74 ATR from the d1 mean
  - AT_HTF_LEVEL: 0.04 ATR to a level
  - RISK_OFF: macro_risk
  - regimes d1/h4/h1: up/up/up, ATR20 89.955, range position 120d 0.32400907152286523

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
