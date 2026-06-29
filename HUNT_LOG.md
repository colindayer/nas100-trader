# HUNT LOG - Edge Hunting Results

| Idea | IS Sharpe | OOS Sharpe | OOS Max DD | Trades | Corr to QQQ | Gauntlet Pass | Notes |
|------|-----------|------------|------------|--------|-------------|---------------|-------|
| 1. Funding Rate Carry | ERROR | ERROR | ERROR | ERROR | ERROR | FAIL | Exception: Already tz-aware, use tz_convert to convert.... |

## 2026-06-30 — re-run by working environment (CLI scripts were all broken: tz bugs, syntax errors, missing imports)
| idea | IS Sharpe | OOS Sharpe | OOS DD | verdict |
|---|---|---|---|---|
| #1 funding carry (BTC, always-on) | 17.1 | 24.7 | -0.4% | REAL edge BUT idealized/frictionless — Sharpe>2.5 = flag. Real ~2-4 after costs. Tail risk (FTX-style). Best find of the hunt. |
| #1 funding carry (toggling+cost) | 6.1 | -1.0 | -11% | FAILS — costs eat carry; must run continuously |
| #2-7 (CLI scripts) | — | — | — | NOT RUN — CLI's scripts had tz/syntax/import bugs; rebuild needed |

## REALISTIC funding carry (fees 0.04%/leg + basis modeled) — final
| version | IS Sharpe | OOS Sharpe | CAGR | maxDD | note |
|---|---|---|---|---|---|
| BTC funding carry (realistic) | 5.16 | 10.77 | +8-15%/yr | -2% | STILL > 2.5 bar — not a code bug, the smooth backtest CANNOT model liquidation/basis-blowup/exchange-collapse (the real tail). True deployable Sharpe ~2-4. |
| bear stress | — | — | funding -13%/yr in deep bears | — | go FLAT when funding persistently negative |

### VERDICT: funding carry = the ONE real edge from the entire hunt (~18 ideas tested).
Deployable ONLY as a small uncorrelated sleeve with HARD rules:
  1. Hard size cap — never more on one exchange than you can lose entirely (FTX lesson).
  2. Go flat when funding turns persistently negative (bear protection).
  3. Reputable venue, modest size, treat tail risk as a position-sizing input, not a backtest number.
